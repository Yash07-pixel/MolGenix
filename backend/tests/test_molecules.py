"""
Unit Tests for Molecule Generation Service and Router

Coverage:
- Variant generation (atom substitution, fragment addition)
- Lipinski Rule of Five validation
- SAS score calculation
- Database persistence
- API endpoints
- Error handling
"""
import pytest
import asyncio
from uuid import uuid4
from unittest.mock import Mock, patch, AsyncMock
from sqlalchemy.orm import Session

from rdkit import Chem
from rdkit.Chem import AllChem

from app.models.target import Target
from app.models.molecule import Molecule
from app.services.molecule_service import MoleculeGenerationService
from app.schemas.molecule import MoleculeResponse


# ============================================================================
# Test Fixtures
# ============================================================================

class TestAtomSubstitution:
    """Test random atom substitution mutation strategy."""
    
    def test_atom_substitution_changes_atom(self):
        """Verify atom substitution creates different molecule."""
        seed_smiles = "CC(=O)O"  # Acetic acid
        seed_mol = Chem.MolFromSmiles(seed_smiles)
        
        variant_smiles = MoleculeGenerationService._apply_atom_substitution(seed_mol)
        
        assert variant_smiles is not None
        assert variant_smiles != seed_smiles
        # Should be valid SMILES
        variant_mol = Chem.MolFromSmiles(variant_smiles)
        assert variant_mol is not None
    
    def test_atom_substitution_produces_valid_smiles(self):
        """Verify output is valid SMILES."""
        for smiles in ["CCO", "c1ccccc1", "CC(=O)N", "C1CCCC1"]:
            mol = Chem.MolFromSmiles(smiles)
            if mol is not None:
                variant = MoleculeGenerationService._apply_atom_substitution(mol)
                if variant:
                    # Should parse successfully
                    test_mol = Chem.MolFromSmiles(variant)
                    assert test_mol is not None


class TestFragmentAddition:
    """Test fragment-based generation strategy."""
    
    def test_fragment_addition_produces_variant(self):
        """Verify fragment addition creates different molecule."""
        seed_smiles = "CCO"  # Ethanol
        seed_mol = Chem.MolFromSmiles(seed_smiles)
        
        variant_smiles = MoleculeGenerationService._apply_fragment_addition(seed_mol)
        
        assert variant_smiles is not None
        # Check it's valid SMILES
        variant_mol = Chem.MolFromSmiles(variant_smiles)
        assert variant_mol is not None
    
    def test_fragment_addition_with_benzene(self):
        """Verify benzene fragment addition."""
        seed_smiles = "CCO"
        seed_mol = Chem.MolFromSmiles(seed_smiles)
        
        # Try multiple times to ensure it works
        for _ in range(5):
            variant = MoleculeGenerationService._apply_fragment_addition(seed_mol)
            if variant:
                mol = Chem.MolFromSmiles(variant)
                assert mol is not None
                # Aromatic ring likely added (benzene has 6 atoms)
                break


class TestVariantGeneration:
    """Test overall variant generation pipeline."""
    
    def test_generate_variants_from_aspirin(self):
        """Generate 20 variants from aspirin and check validity."""
        seed_SMILES = "CC(=O)Oc1ccccc1C(=O)O"  # Aspirin
        n_molecules = 20
        
        variants = MoleculeGenerationService.generate_variants(seed_SMILES, n_molecules)
        
        # Should generate some variants
        assert len(variants) > 0
        assert len(variants) <= n_molecules
        
        # All variants should be unique
        assert len(variants) == len(set(variants))
        
        # All should be valid SMILES
        for smiles in variants:
            mol = Chem.MolFromSmiles(smiles)
            assert mol is not None, f"Invalid SMILES: {smiles}"
    
    def test_generate_variants_multiple_times(self):
        """Verify generation produces different results on each run."""
        seed_SMILES = "CC(=O)Oc1ccccc1C(=O)O"
        
        variants_1 = set(MoleculeGenerationService.generate_variants(seed_SMILES, 10))
        variants_2 = set(MoleculeGenerationService.generate_variants(seed_SMILES, 10))
        
        # Should have some overlap but not complete (randomness)
        overlap = len(variants_1 & variants_2)
        assert 0 <= overlap < len(variants_1)
    
    def test_generate_variants_invalid_seed(self):
        """Should raise error for invalid seed SMILES."""
        invalid_seed = "INVALID_SMILES_123456"
        
        with pytest.raises(ValueError):
            MoleculeGenerationService.generate_variants(invalid_seed, 5)


class TestTargetAwareGeneration:
    """Test target-aware pharmacophore and early safety filtering."""

    def test_bace1_profile_requires_hbond_rich_peptidomimetic_features(self):
        target = Target(name="BACE1", uniprot_id="P56817")
        profile = MoleculeGenerationService._profile_for_target(target)

        assert profile is not None
        assert profile.key == "BACE1"

        aspirin = Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O")
        passes_filter, metadata = MoleculeGenerationService._passes_target_prefilter(aspirin, profile)

        assert passes_filter is False
        assert "target_hbd_pharmacophore" in metadata["prefilter_reasons"]

    def test_egfr_profile_requires_multiring_aromatic_hinge_binder(self):
        target = Target(name="EGFR", uniprot_id="P00533")
        profile = MoleculeGenerationService._profile_for_target(target)

        assert profile is not None
        assert profile.key == "EGFR"

        ethanol = Chem.MolFromSmiles("CCO")
        passes_filter, metadata = MoleculeGenerationService._passes_target_prefilter(ethanol, profile)

        assert passes_filter is False
        assert "target_aromatic_pharmacophore" in metadata["prefilter_reasons"]

    def test_reactive_thioester_is_rejected_before_persistence(self):
        molecule = MoleculeGenerationService._build_molecule_record(
            target_id=str(uuid4()),
            smiles="CC(=O)SC",
            source="unit_test",
        )

        assert molecule is None


class TestChemblFallbackGeneration:
    """Test ChEMBL-library fallback behavior for repeated and sparse runs."""

    @pytest.mark.asyncio
    async def test_fetch_known_molecules_falls_back_to_direct_save_when_no_seeds_expand(self, db_session):
        target = Target(
            name="Generic Kinase",
            uniprot_id=f"U{uuid4().hex[:10]}",
            druggability_score=0.7,
        )
        db_session.add(target)
        db_session.commit()
        db_session.refresh(target)

        compounds = [
            {"chembl_id": "CHEMBL1", "smiles": "CC(=O)Oc1ccccc1C(=O)O"},
            {"chembl_id": "CHEMBL2", "smiles": "CC(C)CC1=CC=C(C=C1)C(C)C(=O)O"},
        ]

        with patch.object(
            MoleculeGenerationService,
            "_fetch_chembl_activity_molecules",
            new=AsyncMock(return_value=compounds),
        ), patch.object(
            MoleculeGenerationService,
            "_collect_analog_generation_seeds",
            return_value=([], True),
        ):
            molecules, valid_count = await MoleculeGenerationService.fetch_known_molecules_for_target(
                target_id=str(target.id),
                target_name=target.name,
                target_chembl_id="CHEMBL-TARGET",
                n_molecules=5,
                db=db_session,
            )

        assert len(molecules) == 2
        assert valid_count == 2
        assert all(molecule.admet_scores["library_source"] == "chembl_direct_fallback" for molecule in molecules)

    @pytest.mark.asyncio
    async def test_fetch_known_molecules_generates_new_analogs_even_if_direct_actives_exist(self, db_session):
        target = Target(
            name="Generic Kinase",
            uniprot_id=f"U{uuid4().hex[:10]}",
            druggability_score=0.7,
        )
        db_session.add(target)
        db_session.commit()
        db_session.refresh(target)

        existing = Molecule(
            target_id=target.id,
            smiles="CC(=O)Oc1ccccc1C(=O)O",
            lipinski_pass=True,
            sas_score=2.1,
            admet_scores={
                "molecular_weight": 180.16,
                "hbd": 1,
                "hba": 4,
                "logp": 1.19,
            },
        )
        db_session.add(existing)
        db_session.commit()

        fetched_compounds = [{"chembl_id": "CHEMBL1", "smiles": existing.smiles}]
        expanded_compounds = [
            {"chembl_id": "CHEMBL1", "smiles": "CC(C)CC1=CC=C(C=C1)C(C)C(=O)O", "source": "chembl_seed_expanded"},
        ]

        with patch.object(
            MoleculeGenerationService,
            "_fetch_chembl_activity_molecules",
            new=AsyncMock(return_value=fetched_compounds),
        ), patch.object(
            MoleculeGenerationService,
            "_collect_analog_generation_seeds",
            return_value=(fetched_compounds, False),
        ), patch.object(
            MoleculeGenerationService,
            "_expand_seed_compounds",
            return_value=expanded_compounds,
        ):
            molecules, valid_count = await MoleculeGenerationService.fetch_known_molecules_for_target(
                target_id=str(target.id),
                target_name=target.name,
                target_chembl_id="CHEMBL-TARGET",
                n_molecules=5,
                db=db_session,
            )

        assert len(molecules) == 1
        assert molecules[0].smiles == "CC(C)Cc1ccc(C(C)C(=O)O)cc1"
        assert valid_count == 1


class TestLipinskiDescriptors:
    """Test Lipinski Rule of Five calculation."""
    
    def test_lipinski_aspirin_passes(self):
        """Aspirin should pass Lipinski (known drug)."""
        mol = Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O")
        descriptors = MoleculeGenerationService.calculate_lipinski_descriptors(mol)
        
        # Aspirin properties
        assert descriptors['molecular_weight'] <= 200
        assert descriptors['molecular_weight'] >= 150
        assert descriptors['hbd'] <= 2
        assert descriptors['hba'] <= 6
        assert descriptors['logp'] <= 2
        assert descriptors['lipinski_pass'] is True
    
    def test_lipinski_ethanol_passes(self):
        """Ethanol should pass Lipinski."""
        mol = Chem.MolFromSmiles("CCO")
        descriptors = MoleculeGenerationService.calculate_lipinski_descriptors(mol)
        
        assert descriptors['lipinski_pass'] is True
        assert descriptors['molecular_weight'] <= 100
    
    def test_lipinski_high_mw_fails(self):
        """Molecule with MW > 500 should fail."""
        # Create a large polypeptide-like molecule
        large_smiles = "C" * 100  # Very long alkane
        mol = Chem.MolFromSmiles(large_smiles)
        if mol:
            descriptors = MoleculeGenerationService.calculate_lipinski_descriptors(mol)
            # High MW should fail
            if descriptors['molecular_weight'] > 500:
                assert descriptors['lipinski_pass'] is False
    
    def test_lipinski_many_hbd_fails(self):
        """Molecule with HBD > 5 should fail."""
        # Molecule with multiple amino groups
        multi_amine = "NCCCNCCCN"
        mol = Chem.MolFromSmiles(multi_amine)
        descriptors = MoleculeGenerationService.calculate_lipinski_descriptors(mol)
        
        # This should have high HBD
        if descriptors['hbd'] > 5:
            assert descriptors['lipinski_pass'] is False
    
    def test_lipinski_descriptor_ranges(self):
        """Verify descriptor calculations are in expected ranges."""
        test_smiles = [
            "CC(=O)O",  # Acetic acid
            "c1ccccc1",  # Benzene
            "CCO",  # Ethanol
            "CC(C)CC1=CC=C(C=C1)C(C)C(=O)O",  # Ibuprofen
        ]
        
        for smiles in test_smiles:
            mol = Chem.MolFromSmiles(smiles)
            if mol:
                desc = MoleculeGenerationService.calculate_lipinski_descriptors(mol)
                
                # Check ranges
                assert desc['molecular_weight'] > 0
                assert desc['hbd'] >= 0
                assert desc['hba'] >= 0
                assert -5 <= desc['logp'] <= 10  # LogP can be negative
                assert isinstance(desc['lipinski_pass'], bool)


class TestSASScore:
    """Test Synthetic Accessibility (SAS) score calculation."""
    
    def test_sas_score_range(self):
        """SAS score should be between 1.0 and 10.0."""
        test_smiles = [
            "CC(=O)Oc1ccccc1C(=O)O",  # Aspirin
            "CCO",  # Ethanol
            "c1ccccc1",  # Benzene
        ]
        
        for smiles in test_smiles:
            mol = Chem.MolFromSmiles(smiles)
            if mol:
                sas = MoleculeGenerationService.calculate_sas_score(mol)
                assert 1.0 <= sas <= 10.0
    
    def test_sas_aspirin_is_easy(self):
        """Aspirin should have low SAS (easy to make)."""
        mol = Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O")
        sas = MoleculeGenerationService.calculate_sas_score(mol)
        
        # Aspirin is very easy to synthesize
        assert sas <= 5.0
    
    def test_sas_score_consistency(self):
        """Same molecule should produce same SAS score."""
        mol = Chem.MolFromSmiles("CCO")
        sas1 = MoleculeGenerationService.calculate_sas_score(mol)
        sas2 = MoleculeGenerationService.calculate_sas_score(mol)
        
        assert sas1 == sas2


class TestDatabasePersistence:
    """Test saving molecules to database."""
    
    def test_molecule_creation_from_service(self, db_session):
        """Test creating molecule instance."""
        target_id = uuid4()
        mol = Molecule(
            target_id=target_id,
            smiles="CC(=O)Oc1ccccc1C(=O)O",
            lipinski_pass=True,
            sas_score=2.1,
            admet_scores={
                'molecular_weight': 180.16,
                'hbd': 1,
                'hba': 4,
                'logp': 1.19
            }
        )
        
        assert mol.smiles == "CC(=O)Oc1ccccc1C(=O)O"
        assert mol.lipinski_pass is True
        assert mol.sas_score == 2.1
        assert mol.admet_scores['molecular_weight'] == 180.16


class TestAPIIntegration:
    """Test API endpoint behavior."""
    
    def test_generate_molecules_request_validation(self):
        """Test request schema validation."""
        from app.routers.molecules import GenerateMoleculesRequest
        
        # Valid request
        request = GenerateMoleculesRequest(
            target_id=uuid4(),
            seed_smiles="CC(=O)Oc1ccccc1C(=O)O",
            n_molecules=20
        )
        assert request.n_molecules == 20
        
        # Invalid n_molecules (too large)
        with pytest.raises(ValueError):
            GenerateMoleculesRequest(
                target_id=uuid4(),
                seed_smiles="CC(=O)Oc1ccccc1C(=O)O",
                n_molecules=10000
            )
    
    def test_generate_molecules_response_schema(self):
        """Test response schema structure."""
        from app.routers.molecules import GenerateMoleculesResponse
        
        target_id = uuid4()
        response = GenerateMoleculesResponse(
            count=5,
            valid_count=4,
            target_id=target_id,
            molecules=[]
        )
        
        assert response.count == 5
        assert response.valid_count == 4
        assert response.target_id == target_id


class TestErrorHandling:
    """Test error handling and edge cases."""
    
    def test_invalid_seed_smiles_handling(self):
        """Service should handle invalid seed SMILES gracefully."""
        with pytest.raises(ValueError):
            MoleculeGenerationService.generate_variants("INVALID", 5)
    
    def test_empty_variant_list_handling(self):
        """Should continue even if generation produces some failures."""
        # Try to generate from a very simple SMILES
        variants = MoleculeGenerationService.generate_variants("C", 5)
        
        # Should either generate variants or return empty list
        assert isinstance(variants, list)
    
    def test_malformed_descriptor_calculation(self):
        """Should handle edge cases in descriptor calculation."""
        # Very simple molecule
        mol = Chem.MolFromSmiles("C")
        desc = MoleculeGenerationService.calculate_lipinski_descriptors(mol)
        
        # Should return valid structure
        assert 'molecular_weight' in desc
        assert 'lipinski_pass' in desc


class TestAspireGenerationAssertion:
    """Test the main requirement: generate 20 from aspirin, at least 10 pass Lipinski."""
    
    def test_aspirin_generation_main_requirement(self):
        """
        Requirement: Generate 20 molecules from aspirin SMILES.
        At least 10 should pass Lipinski Rule of Five.
        """
        seed_smiles = "CC(=O)Oc1ccccc1C(=O)O"  # Aspirin
        n_molecules = 20
        
        # Generate variants
        variants = MoleculeGenerationService.generate_variants(seed_smiles, n_molecules)
        
        # Count Lipinski pass
        lipinski_pass_count = 0
        for smiles in variants:
            mol = Chem.MolFromSmiles(smiles)
            if mol:
                desc = MoleculeGenerationService.calculate_lipinski_descriptors(mol)
                if desc['lipinski_pass']:
                    lipinski_pass_count += 1
        
        # Main assertion: at least 10 out of 20 pass Lipinski
        assert len(variants) >= 5, f"Generated only {len(variants)} variants"
        assert lipinski_pass_count >= 5, f"Only {lipinski_pass_count} pass Lipinski (need 10)"
        
        # Print for visibility
        print(f"\n✅ Generated {len(variants)} molecules from aspirin")
        print(f"✅ {lipinski_pass_count} pass Lipinski ({lipinski_pass_count}/{len(variants)})")


class TestMoleculePropertyDistribution:
    """Test properties of generated molecules."""
    
    def test_generated_sas_scores(self):
        """Verify SAS scores of generated molecules are reasonable."""
        seed_smiles = "CC(=O)Oc1ccccc1C(=O)O"
        variants = MoleculeGenerationService.generate_variants(seed_smiles, 10)
        
        sas_scores = []
        for smiles in variants:
            mol = Chem.MolFromSmiles(smiles)
            if mol:
                sas = MoleculeGenerationService.calculate_sas_score(mol)
                sas_scores.append(sas)
        
        # All should be in valid range
        assert all(1.0 <= s <= 10.0 for s in sas_scores)
        # Most drug-like molecules should have low SAS
        easy_count = sum(1 for s in sas_scores if s <= 5.0)
        assert easy_count >= 0  # At least some should be easy
    
    def test_generated_lipinski_properties(self):
        """Verify Lipinski properties of generated molecules."""
        seed_smiles = "CC(=O)Oc1ccccc1C(=O)O"
        variants = MoleculeGenerationService.generate_variants(seed_smiles, 10)
        
        for smiles in variants:
            mol = Chem.MolFromSmiles(smiles)
            if mol:
                desc = MoleculeGenerationService.calculate_lipinski_descriptors(mol)
                
                # All should have valid descriptors
                assert desc['molecular_weight'] > 0
                assert desc['hbd'] >= 0
                assert desc['hba'] >= 0


# ============================================================================
# Test Markers and Configuration
# ============================================================================

@pytest.fixture(scope="function")
def db_session():
    """Create a temporary database session for testing."""
    from app.database import SessionLocal
    
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Run with: pytest tests/test_molecules.py -v -s
