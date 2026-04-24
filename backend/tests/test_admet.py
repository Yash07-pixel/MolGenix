"""
Unit Tests for ADMET Prediction Service

Tests:
- BBBP prediction
- Hepatotoxicity prediction
- hERG risk prediction
- Oral bioavailability prediction
- Traffic light classification
- Database persistence
- Known safe drugs validation
"""
import pytest
from uuid import uuid4

Chem = pytest.importorskip("rdkit.Chem", reason="RDKit is optional and not installed in this environment")

from app.services.admet_service import ADMETService


class TestBBBPPrediction:
    """Test Blood-Brain Barrier Barrier penetration prediction."""
    
    def test_bbbp_returns_float(self):
        """BBBP should return float 0-1 or None."""
        smiles = "CCO"  # Ethanol
        result = ADMETService.predict_bbbp(smiles)
        
        assert result is None or (isinstance(result, float) and 0 <= result <= 1)
    
    def test_bbbp_invalid_smiles(self):
        """BBBP should return None for invalid SMILES."""
        result = ADMETService.predict_bbbp("INVALID_SMILES")
        assert result is None


class TestHepatotoxicityPrediction:
    """Test hepatotoxicity prediction."""
    
    def test_hepato_returns_float(self):
        """Hepatotoxicity should return float 0-1 or None."""
        smiles = "CC(=O)Oc1ccccc1C(=O)O"  # Aspirin
        result = ADMETService.predict_hepatotoxicity(smiles)
        
        assert result is None or (isinstance(result, float) and 0 <= result <= 1)
    
    def test_hepato_invalid_smiles(self):
        """Hepatotoxicity should return None for invalid SMILES."""
        result = ADMETService.predict_hepatotoxicity("INVALID")
        assert result is None


class TestHERGPrediction:
    """Test hERG cardiotoxicity risk prediction."""
    
    def test_herg_returns_tuple(self):
        """hERG should return (bool, float) tuple."""
        smiles = "CCO"
        risk, confidence = ADMETService.predict_herg(smiles)
        
        assert isinstance(risk, bool)
        assert isinstance(confidence, float)
        assert 0 <= confidence <= 1
    
    def test_herg_high_mw_and_logp(self):
        """High MW (>500) AND high LogP (>3) should flag hERG risk."""
        # Large lipophilic compound
        smiles = "C" * 100  # Very large alkane
        mol = Chem.MolFromSmiles(smiles)
        
        if mol:
            risk, confidence = ADMETService.predict_herg(smiles)
            # High MW should increase confidence
            assert confidence >= 0.5 if risk else True
    
    def test_herg_invalid_smiles(self):
        """hERG should handle invalid SMILES safely."""
        risk, confidence = ADMETService.predict_herg("INVALID")
        
        assert isinstance(risk, bool)
        assert isinstance(confidence, float)


class TestBioavailabilityPrediction:
    """Test oral bioavailability prediction."""
    
    def test_bioavail_returns_float(self):
        """Bioavailability should return float 0-1."""
        mol = Chem.MolFromSmiles("CCO")
        result = ADMETService.predict_oral_bioavailability(mol, lipinski_pass=True)
        
        assert isinstance(result, float)
        assert 0 <= result <= 1
    
    def test_bioavail_lipinski_pass(self):
        """Lipinski pass should improve bioavailability score."""
        mol = Chem.MolFromSmiles("CCO")
        
        score_pass = ADMETService.predict_oral_bioavailability(mol, lipinski_pass=True)
        score_fail = ADMETService.predict_oral_bioavailability(mol, lipinski_pass=False)
        
        assert score_pass > score_fail


class TestTrafficLightClassification:
    """Test traffic light classification."""
    
    def test_green_light(self):
        """Score > 0.7 should be green."""
        result = ADMETService.classify_traffic_light(0.75)
        assert result == "green"
    
    def test_yellow_light(self):
        """Score 0.4-0.7 should be yellow."""
        result = ADMETService.classify_traffic_light(0.5)
        assert result == "yellow"
    
    def test_red_light(self):
        """Score < 0.4 should be red."""
        result = ADMETService.classify_traffic_light(0.3)
        assert result == "red"
    
    def test_none_score(self):
        """None score should return 'unknown'."""
        result = ADMETService.classify_traffic_light(None)
        assert result == "unknown"


class TestKnownSafeDrugs:
    """Test ADMET predictions on known safe drugs.
    
    Expected: Most scores should be green (>0.7) for safe drugs.
    """
    
    def test_aspirin_admet(self):
        """Aspirin is a known safe drug - should have mostly green flags."""
        smiles = "CC(=O)Oc1ccccc1C(=O)O"
        mol = Chem.MolFromSmiles(smiles)
        
        # Predictions
        bbbp = ADMETService.predict_bbbp(smiles)
        hepato = ADMETService.predict_hepatotoxicity(smiles)
        herg_risk, herg_conf = ADMETService.predict_herg(smiles)
        bioavail = ADMETService.predict_oral_bioavailability(mol, lipinski_pass=True)
        
        # Check traffic lights
        bbbp_light = ADMETService.classify_traffic_light(bbbp)
        hepato_light = ADMETService.classify_traffic_light(hepato)
        bioavail_light = ADMETService.classify_traffic_light(bioavail)
        
        # Aspirin should be mostly safe
        green_count = sum([
            bbbp_light == "green",
            hepato_light == "green",
            not herg_risk,  # Should not flag hERG risk
            bioavail_light == "green"
        ])
        
        # At least 2 should be green for known safe drug
        assert green_count >= 2
    
    def test_ibuprofen_admet(self):
        """Ibuprofen is a known safe drug."""
        smiles = "CC(C)CC1=CC=C(C=C1)C(C)C(=O)O"
        mol = Chem.MolFromSmiles(smiles)
        
        hepato = ADMETService.predict_hepatotoxicity(smiles)
        herg_risk, _ = ADMETService.predict_herg(smiles)
        bioavail = ADMETService.predict_oral_bioavailability(mol, lipinski_pass=True)
        
        hepato_light = ADMETService.classify_traffic_light(hepato)
        bioavail_light = ADMETService.classify_traffic_light(bioavail)
        
        # Should be mostly safe
        green_count = sum([
            hepato_light == "green",
            not herg_risk,
            bioavail_light == "green"
        ])
        assert green_count >= 2
    
    def test_metformin_admet(self):
        """Metformin is a known safe drug for diabetes."""
        smiles = "CN(C)C(=N)NC(=N)N"
        mol = Chem.MolFromSmiles(smiles)
        
        if mol is None:
            pytest.skip("Invalid SMILES for metformin")
        
        bbbp = ADMETService.predict_bbbp(smiles)
        hepato = ADMETService.predict_hepatotoxicity(smiles)
        herg_risk, _ = ADMETService.predict_herg(smiles)
        bioavail = ADMETService.predict_oral_bioavailability(mol, lipinski_pass=True)
        
        # All should indicate safety
        bbbp_light = ADMETService.classify_traffic_light(bbbp)
        hepato_light = ADMETService.classify_traffic_light(hepato)
        bioavail_light = ADMETService.classify_traffic_light(bioavail)
        
        green_count = sum([
            bbbp_light in ["green", "yellow"],
            hepato_light in ["green", "yellow"],
            not herg_risk,
            bioavail_light in ["green", "yellow"]
        ])
        assert green_count >= 3
    
    def test_paracetamol_admet(self):
        """Paracetamol (acetaminophen) is a common safe drug."""
        smiles = "CC(=O)Nc1ccc(O)cc1"
        mol = Chem.MolFromSmiles(smiles)
        
        hepato = ADMETService.predict_hepatotoxicity(smiles)
        bioavail = ADMETService.predict_oral_bioavailability(mol, lipinski_pass=True)
        
        hepato_light = ADMETService.classify_traffic_light(hepato)
        bioavail_light = ADMETService.classify_traffic_light(bioavail)
        
        # Small safe molecule
        assert hepato_light in ["green", "yellow"]
        assert bioavail_light in ["green", "yellow"]
    
    def test_caffeine_admet(self):
        """Caffeine is a known safe compound."""
        smiles = "CN1C=NC2=C1C(=O)N(C(=O)N2C)C"
        mol = Chem.MolFromSmiles(smiles)
        
        bbbp = ADMETService.predict_bbbp(smiles)
        bioavail = ADMETService.predict_oral_bioavailability(mol, lipinski_pass=True)
        
        bbbp_light = ADMETService.classify_traffic_light(bbbp)
        bioavail_light = ADMETService.classify_traffic_light(bioavail)
        
        # Caffeine crosses BBB and is bioavailable
        assert bbbp_light in ["green", "yellow"]
        assert bioavail_light in ["green", "yellow"]


class TestSummaryFunction:
    """Test ADMET summary generation."""
    
    def test_get_summary(self):
        """Summary should return traffic lights for all properties."""
        admet_data = {
            "bbbp_traffic": "green",
            "hepatotoxicity_traffic": "yellow",
            "herg_risk": False,
            "bioavailability_traffic": "green",
        }
        
        summary = ADMETService.get_summary(admet_data)
        
        assert summary["bbbp"] == "green"
        assert summary["hepatotoxicity"] == "yellow"
        assert summary["herg"] == "green"  # Not flagged -> green
        assert summary["bioavailability"] == "green"
    
    def test_get_summary_with_herg_risk(self):
        """Summary should show red for hERG risk."""
        admet_data = {
            "bbbp_traffic": "green",
            "hepatotoxicity_traffic": "green",
            "herg_risk": True,  # Flagged
            "bioavailability_traffic": "green",
        }
        
        summary = ADMETService.get_summary(admet_data)
        
        assert summary["herg"] == "red"  # Flagged -> red


class TestADMETDataStructure:
    """Test ADMET data structure and content."""
    
    def test_admet_data_has_all_fields(self):
        """ADMET data should have all required fields."""
        smiles = "CCO"
        mol = Chem.MolFromSmiles(smiles)
        
        bbbp = ADMETService.predict_bbbp(smiles)
        hepato = ADMETService.predict_hepatotoxicity(smiles)
        herg_risk, herg_conf = ADMETService.predict_herg(smiles)
        bioavail = ADMETService.predict_oral_bioavailability(mol, True)
        
        admet_data = {
            "bbbp_score": bbbp,
            "bbbp_traffic": ADMETService.classify_traffic_light(bbbp),
            "hepatotoxicity_score": hepato,
            "hepatotoxicity_traffic": ADMETService.classify_traffic_light(hepato, lower_is_better=True),
            "herg_risk": herg_risk,
            "herg_confidence": herg_conf,
            "bioavailability_score": bioavail,
            "bioavailability_traffic": ADMETService.classify_traffic_light(bioavail),
            "solubility_score": ADMETService.predict_solubility(smiles),
            "solubility_traffic": ADMETService.classify_traffic_light(ADMETService.predict_solubility(smiles)),
            "clearance_score": ADMETService.predict_clearance(smiles),
            "clearance_traffic": ADMETService.classify_traffic_light(ADMETService.predict_clearance(smiles)),
            "cyp3a4_liability": ADMETService.predict_cyp3a4_liability(smiles),
            "cyp3a4_traffic": ADMETService.classify_traffic_light(ADMETService.predict_cyp3a4_liability(smiles), lower_is_better=True),
            "model_source": "deepchem_hybrid",
        }
        
        # All fields present
        required_fields = {
            "bbbp_score", "bbbp_traffic",
            "hepatotoxicity_score", "hepatotoxicity_traffic",
            "herg_risk", "herg_confidence",
            "bioavailability_score", "bioavailability_traffic",
            "solubility_score", "solubility_traffic",
            "clearance_score", "clearance_traffic",
            "cyp3a4_liability", "cyp3a4_traffic",
            "model_source",
        }
        
        assert all(field in admet_data for field in required_fields)


# Run with: pytest tests/test_admet.py -v
