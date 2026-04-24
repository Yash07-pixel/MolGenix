"""
Lead Optimization Service - RDKit-based R-group substitution and rescoring.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem

    RDKIT_AVAILABLE = True
except ImportError:
    Chem = None
    AllChem = None
    RDKIT_AVAILABLE = False

logger = logging.getLogger(__name__)

R_GROUPS: List[tuple[str, str]] = [
    ("F", "F"),
    ("Cl", "Cl"),
    ("CF3", "C(F)(F)F"),
    ("OCH3", "OC"),
    ("NH2", "N"),
    ("COOH", "C(=O)O"),
    ("CN", "C#N"),
    ("OH", "O"),
    ("CH3", "C"),
    ("NO2", "[N+](=O)[O-]"),
]

REACTION_TEMPLATES: List[tuple[str, str, str, str]] = [
    ("aromatic ring", "[cH:1]", "[c:1]{fragment}", "Added {label} on aromatic ring site {site}"),
    ("NH group", "[N;H1,H2:1]", "[N:1]{fragment}", "Substituted NH with {label} at site {site}"),
    ("OH group", "[O;H1:1]", "[O:1]{fragment}", "Substituted OH with {label} at site {site}"),
]


class OptimizationService:
    """Optimize a lead molecule by generating and rescoring R-group variants."""

    @staticmethod
    def _require_rdkit() -> None:
        if not RDKIT_AVAILABLE:
            raise RuntimeError("RDKit is required for lead optimization")

    @staticmethod
    def _score_smiles(smiles: str) -> Dict[str, Any]:
        """Calculate Lipinski, SAS, ADMET, and combined score for a SMILES."""
        OptimizationService._require_rdkit()
        from app.services.admet_service import ADMETService
        from app.services.molecule_service import MoleculeGenerationService

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError(f"Invalid SMILES: {smiles}")

        lipinski_data = MoleculeGenerationService.calculate_lipinski_descriptors(mol)
        sas_score = MoleculeGenerationService.calculate_sas_score(mol)

        bbbp_score = ADMETService.predict_bbbp(smiles)
        hepatotox_score = ADMETService.predict_hepatotoxicity(smiles)
        herg_risk, herg_confidence = ADMETService.predict_herg(smiles)
        bioavailability_score = ADMETService.predict_oral_bioavailability(mol, lipinski_data["lipinski_pass"])

        admet_scores = {
            "bbbp_score": bbbp_score,
            "bbbp_traffic": ADMETService.classify_traffic_light(bbbp_score),
            "hepatotoxicity_score": hepatotox_score,
            "hepatotoxicity_traffic": ADMETService.classify_traffic_light(hepatotox_score),
            "herg_risk": herg_risk,
            "herg_confidence": herg_confidence,
            "bioavailability_score": bioavailability_score,
            "bioavailability_traffic": ADMETService.classify_traffic_light(bioavailability_score),
        }

        admet_green_count = sum(
            [
                admet_scores["bbbp_traffic"] == "green",
                admet_scores["hepatotoxicity_traffic"] == "green",
                not herg_risk,
                admet_scores["bioavailability_traffic"] == "green",
            ]
        )

        combined_score = (
            (1 - sas_score / 10.0) * 0.4
            + float(lipinski_data["lipinski_pass"]) * 0.3
            + (admet_green_count / 4.0) * 0.3
        )

        return {
            "smiles": smiles,
            "sas_score": sas_score,
            "lipinski_pass": lipinski_data["lipinski_pass"],
            "admet_scores": admet_scores,
            "combined_score": round(combined_score, 4),
            "admet_green_count": admet_green_count,
        }

    @staticmethod
    def _generate_substituted_variants(smiles: str, max_variants: int = 10) -> List[Dict[str, Any]]:
        """Generate up to max_variants valid R-group substitutions."""
        OptimizationService._require_rdkit()

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError("Invalid original SMILES")

        variants: List[Dict[str, Any]] = []
        seen: set[str] = set()

        for site_label, reactant_pattern, product_pattern, description_template in REACTION_TEMPLATES:
            pattern = Chem.MolFromSmarts(reactant_pattern)
            matches = mol.GetSubstructMatches(pattern)
            if not matches:
                continue

            for label, fragment in R_GROUPS:
                reaction_smarts = f"{reactant_pattern}>>{product_pattern.format(fragment=fragment)}"
                reaction = AllChem.ReactionFromSmarts(reaction_smarts)
                if reaction is None:
                    continue

                try:
                    product_sets = reaction.RunReactants((mol,))
                except Exception as exc:
                    logger.debug("Reaction failed for %s on %s: %s", label, site_label, exc)
                    continue

                for product_index, products in enumerate(product_sets, start=1):
                    product = products[0]
                    try:
                        Chem.SanitizeMol(product)
                    except Exception:
                        continue

                    variant_smiles = Chem.MolToSmiles(product, canonical=True)
                    if not variant_smiles or variant_smiles == smiles or variant_smiles in seen:
                        continue

                    if Chem.MolFromSmiles(variant_smiles) is None:
                        continue

                    site_number = ((product_index - 1) % len(matches)) + 1
                    variants.append(
                        {
                            "smiles": variant_smiles,
                            "changes": [description_template.format(label=label, site=site_number)],
                        }
                    )
                    seen.add(variant_smiles)

                    if len(variants) >= max_variants:
                        return variants

        return variants

    @staticmethod
    def optimize_smiles(smiles: str) -> Dict[str, Any]:
        """Optimize a SMILES string and return original and best variant details."""
        original = OptimizationService._score_smiles(smiles)
        variants = OptimizationService._generate_substituted_variants(smiles, max_variants=10)
        if not variants:
            raise ValueError("No valid optimization variants could be generated")

        scored_variants: List[Dict[str, Any]] = []
        for variant in variants:
            try:
                scored = OptimizationService._score_smiles(variant["smiles"])
            except Exception as exc:
                logger.debug("Skipping invalid optimized variant %s: %s", variant["smiles"], exc)
                continue

            scored["changes"] = variant["changes"]
            scored_variants.append(scored)

        if not scored_variants:
            raise ValueError("No valid optimization variants could be scored")

        top_variant = max(
            scored_variants,
            key=lambda item: (item["combined_score"], item["lipinski_pass"], -item["sas_score"]),
        )

        return {
            "original": {
                "smiles": original["smiles"],
                "sas_score": original["sas_score"],
                "lipinski_pass": original["lipinski_pass"],
                "admet_scores": original["admet_scores"],
                "docking_score": None,
            },
            "optimized": {
                "smiles": top_variant["smiles"],
                "sas_score": top_variant["sas_score"],
                "lipinski_pass": top_variant["lipinski_pass"],
                "admet_scores": top_variant["admet_scores"],
                "combined_score": top_variant["combined_score"],
            },
            "changes": top_variant["changes"],
        }

    @staticmethod
    async def optimize_molecule(molecule_id: str, db: Any) -> Dict[str, Any]:
        """Optimize a stored molecule and persist the top variant as a new record."""
        from app.models.molecule import Molecule

        molecule = db.query(Molecule).filter(Molecule.id == molecule_id).first()
        if not molecule:
            raise ValueError("Molecule not found")

        optimization_result = OptimizationService.optimize_smiles(molecule.smiles)
        optimization_result["original"]["docking_score"] = molecule.docking_score

        optimized = optimization_result["optimized"]
        optimized_molecule = Molecule(
            target_id=molecule.target_id,
            smiles=optimized["smiles"],
            lipinski_pass=optimized["lipinski_pass"],
            sas_score=optimized["sas_score"],
            admet_scores=optimized["admet_scores"],
            docking_score=None,
            is_optimized=True,
            optimization_changes=optimization_result["changes"],
        )

        db.add(optimized_molecule)
        db.commit()
        db.refresh(optimized_molecule)

        optimized["molecule_id"] = str(optimized_molecule.id)
        return optimization_result
