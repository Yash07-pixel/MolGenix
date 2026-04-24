"""
Lead Optimization Service - RDKit-based medicinal chemistry refinement.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem

    RDKIT_AVAILABLE = True
except ImportError:
    Chem = None
    AllChem = None
    RDKIT_AVAILABLE = False

logger = logging.getLogger(__name__)

# FIXED
BIOISOSTERIC_TRANSFORMS: List[Tuple[str, str, str, str]] = [
    ("COOH_to_SO2NH2", "C(=O)[O;H,-]", "S(=O)(=O)N", "Replaced carboxylic acid with sulfonamide bioisostere"),
    ("COOH_to_tetrazole", "C(=O)[O;H,-]", "c1nnnn1", "Replaced carboxylic acid with tetrazole bioisostere"),
    ("OH_to_F", "[OX2H]", "F", "Replaced hydroxyl with fluorine to tune permeability"),
    ("phenyl_to_pyridine", "c1ccccc1", "c1ccncc1", "Replaced phenyl with pyridine heteroaromatic"),
    ("phenyl_to_thiophene", "c1ccccc1", "c1ccsc1", "Replaced phenyl with thiophene heteroaromatic"),
    ("phenyl_to_furan", "c1ccccc1", "c1ccoc1", "Replaced phenyl with furan heteroaromatic"),
]

# FIXED
HIGH_LOGP_TUNING_TRANSFORMS: List[Tuple[str, str, str, str]] = [
    ("phenyl_to_hydroxypyridine", "c1ccccc1", "c1cc(O)ncc1", "Introduced hydroxypyridine to reduce lipophilicity"),
    ("phenyl_to_aminopyridine", "c1ccccc1", "Nc1ccncc1", "Introduced aminopyridine to add polarity"),
    ("methyl_to_hydroxymethyl", "[CH3]", "CO", "Converted methyl substituent into hydroxymethyl"),
]

# FIXED
LOW_LOGP_TUNING_TRANSFORMS: List[Tuple[str, str, str, str]] = [
    ("OH_to_methoxy", "[OX2H]", "OC", "Methylated hydroxyl to improve lipophilicity"),
    ("phenyl_to_tolyl", "c1ccccc1", "Cc1ccccc1", "Added methyl-substituted phenyl ring"),
    ("phenyl_to_chlorophenyl", "c1ccccc1", "Clc1ccccc1", "Introduced halogenated aromatic ring"),
]

# FIXED
HBOND_OPTIMIZATION_TRANSFORMS: List[Tuple[str, str, str, str]] = [
    ("phenyl_to_aminophenyl", "c1ccccc1", "Nc1ccccc1", "Added aromatic amine to increase hydrogen-bond donation"),
    ("phenyl_to_pyridyl", "c1ccccc1", "c1ccncc1", "Added heteroaromatic acceptor to increase HBA count"),
    ("OH_to_F_reduced_hbd", "[OX2H]", "F", "Removed hydrogen-bond donor to rebalance polarity"),
]


class OptimizationService:
    """Optimize a lead molecule by applying medicinal chemistry transformations."""

    # FIXED
    @staticmethod
    def _require_rdkit() -> None:
        if not RDKIT_AVAILABLE:
            raise RuntimeError("RDKit is required for lead optimization")

    # FIXED
    @staticmethod
    def _optimization_quality(docking_score: float | None) -> str:
        if docking_score is None:
            return "weak_starting_point"
        if docking_score < -8:
            return "strong"
        if docking_score < -6.5:
            return "moderate"
        return "weak_starting_point"

    # FIXED
    @staticmethod
    def select_candidates_for_optimization(molecules: Sequence[Any]) -> List[Any]:
        """Always optimize the best-ranked docked molecules rather than using a hard score cutoff."""
        sorted_molecules = sorted(
            [molecule for molecule in molecules if getattr(molecule, "docking_score", None) is not None],
            key=lambda molecule: molecule.docking_score,
        )
        return list(sorted_molecules[:3])

    # FIXED
    @staticmethod
    def _property_objective_score(metrics: Dict[str, Any], baseline: Optional[Dict[str, Any]] = None) -> float:
        """Use property improvement rather than re-docking as the optimization objective."""
        lipinski_bonus = 1.5 if metrics["lipinski_pass"] else 0.0
        mw_score = max(0.0, 1.0 - abs(float(metrics["molecular_weight"]) - 350.0) / 250.0)
        logp_score = max(0.0, 1.0 - abs(float(metrics["logp"]) - 2.8) / 3.0)
        tpsa_score = max(0.0, 1.0 - min(float(metrics["tpsa"]), 150.0) / 150.0)
        rotatable_score = max(0.0, 1.0 - min(float(metrics["rotatable_bonds"]), 12.0) / 12.0)
        sas_score = max(0.0, 1.0 - min(float(metrics["sas_score"]), 10.0) / 10.0)
        admet_score = float(metrics["admet_green_count"]) / 4.0

        total = lipinski_bonus + mw_score + logp_score + tpsa_score + rotatable_score + sas_score + admet_score

        if baseline is not None:
            if baseline["logp"] > 4.0 and metrics["logp"] < baseline["logp"]:
                total += 0.4
            if baseline["logp"] < 1.0 and metrics["logp"] > baseline["logp"]:
                total += 0.4
            if baseline["hbd"] < 2 and metrics["hbd"] > baseline["hbd"]:
                total += 0.25
            if baseline["hba"] < 4 and metrics["hba"] > baseline["hba"]:
                total += 0.25
            if metrics["sas_score"] <= baseline["sas_score"]:
                total += 0.2

        return round(total, 4)

    # FIXED
    @staticmethod
    def _score_smiles(smiles: str) -> Dict[str, Any]:
        """Calculate RDKit properties, Lipinski status, SAS, ADMET, and property-based optimization score."""
        OptimizationService._require_rdkit()
        from app.services.admet_service import ADMETService
        from app.services.molecule_service import MoleculeGenerationService

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError(f"Invalid SMILES: {smiles}")

        properties = MoleculeGenerationService.compute_properties_from_smiles(smiles)
        if not properties["smiles_valid"]:
            raise ValueError(f"Invalid SMILES: {smiles}")

        lipinski_data = MoleculeGenerationService.calculate_lipinski_descriptors(mol, properties)
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

        scored = {
            "smiles": smiles,
            "molecular_weight": float(properties["mw"]),
            "logp": float(properties["logp"]),
            "hbd": int(properties["hbd"]),
            "hba": int(properties["hba"]),
            "tpsa": float(properties["tpsa"]),
            "rotatable_bonds": int(properties["rotatable_bonds"]),
            "smiles_valid": bool(properties["smiles_valid"]),
            "sas_score": sas_score,
            "lipinski_pass": lipinski_data["lipinski_pass"],
            "strict_lipinski_pass": lipinski_data["strict_lipinski_pass"],
            "lipinski_violations": lipinski_data["lipinski_violations"],
            "admet_scores": admet_scores,
            "admet_green_count": admet_green_count,
        }
        scored["combined_score"] = OptimizationService._property_objective_score(scored)
        return scored

    # FIXED
    @staticmethod
    def _apply_replace_substructs(
        mol: Chem.Mol,
        query_smarts: str,
        replacement_smiles: str,
        description: str,
        max_variants: int = 4,
    ) -> List[Dict[str, Any]]:
        """Apply a SMARTS-based transformation using RDKit ReplaceSubstructs."""
        OptimizationService._require_rdkit()

        query = Chem.MolFromSmarts(query_smarts)
        replacement = Chem.MolFromSmiles(replacement_smiles)
        if query is None or replacement is None:
            return []

        try:
            replaced_sets = AllChem.ReplaceSubstructs(mol, query, replacement, replaceAll=False)
        except Exception as exc:
            logger.debug("ReplaceSubstructs failed for %s -> %s: %s", query_smarts, replacement_smiles, exc)
            return []

        variants: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for replaced in replaced_sets:
            if replaced is None:
                continue
            try:
                Chem.SanitizeMol(replaced)
            except Exception:
                continue

            variant_smiles = Chem.MolToSmiles(replaced, canonical=True)
            if not variant_smiles or variant_smiles in seen:
                continue

            seen.add(variant_smiles)
            variants.append(
                {
                    "smiles": variant_smiles,
                    "changes": [description],
                }
            )
            if len(variants) >= max_variants:
                break

        return variants

    # FIXED
    @staticmethod
    def _build_strategy_plan(original_metrics: Dict[str, Any]) -> List[Tuple[str, List[Tuple[str, str, str, str]]]]:
        """Build ordered medicinal chemistry strategies for the current lead."""
        strategies: List[Tuple[str, List[Tuple[str, str, str, str]]]] = [
            ("bioisosteric_replacement", BIOISOSTERIC_TRANSFORMS),
        ]

        if original_metrics["logp"] > 4.0:
            strategies.append(("lipophilicity_tuning", HIGH_LOGP_TUNING_TRANSFORMS))
        elif original_metrics["logp"] < 1.0:
            strategies.append(("lipophilicity_tuning", LOW_LOGP_TUNING_TRANSFORMS))
        else:
            strategies.append(("lipophilicity_tuning", HIGH_LOGP_TUNING_TRANSFORMS[:2] + LOW_LOGP_TUNING_TRANSFORMS[:1]))

        strategies.append(("hydrogen_bond_optimization", HBOND_OPTIMIZATION_TRANSFORMS))
        return strategies

    # FIXED
    @staticmethod
    def _score_variant_against_baseline(
        variant: Dict[str, Any],
        baseline: Dict[str, Any],
        strategy_name: str,
    ) -> Optional[Dict[str, Any]]:
        try:
            scored = OptimizationService._score_smiles(variant["smiles"])
        except Exception as exc:
            logger.debug("Skipping invalid optimized variant %s: %s", variant["smiles"], exc)
            return None

        scored["combined_score"] = OptimizationService._property_objective_score(scored, baseline)
        scored["changes"] = list(variant.get("changes", []))
        scored["strategy_used"] = strategy_name
        return scored

    # FIXED
    @staticmethod
    def optimize_smiles(smiles: str, docking_score: float | None = None) -> Dict[str, Any]:
        """Optimize a SMILES string and always return a best-effort optimized result."""
        original = OptimizationService._score_smiles(smiles)
        starting_quality = OptimizationService._optimization_quality(docking_score)
        original["docking_score"] = docking_score

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError("Invalid original SMILES")

        baseline_score = float(original["combined_score"])
        selected_variant: Optional[Dict[str, Any]] = None
        fallback_best_variant: Optional[Dict[str, Any]] = None

        for strategy_name, transforms in OptimizationService._build_strategy_plan(original):
            strategy_best: Optional[Dict[str, Any]] = None

            for _transform_label, query_smarts, replacement_smiles, description in transforms:
                variants = OptimizationService._apply_replace_substructs(
                    mol,
                    query_smarts,
                    replacement_smiles,
                    description,
                )
                for variant in variants:
                    if variant["smiles"] == original["smiles"]:
                        continue
                    scored_variant = OptimizationService._score_variant_against_baseline(variant, original, strategy_name)
                    if scored_variant is None:
                        continue

                    if fallback_best_variant is None or scored_variant["combined_score"] > fallback_best_variant["combined_score"]:
                        fallback_best_variant = scored_variant
                    if strategy_best is None or scored_variant["combined_score"] > strategy_best["combined_score"]:
                        strategy_best = scored_variant

            if strategy_best is not None and strategy_best["combined_score"] > baseline_score:
                selected_variant = strategy_best
                break

        if selected_variant is None:
            selected_variant = fallback_best_variant

        if selected_variant is None:
            selected_variant = {
                **original,
                "changes": [
                    "No chemically valid modifications were generated; returning the original scaffold as the optimization baseline."
                ],
                "strategy_used": "fallback_no_valid_transform",
            }

        optimization_note = (
            "Optimization performed on weak starting point - experimental validation essential"
            if starting_quality == "weak_starting_point"
            else None
        )

        return {
            "original": {
                "smiles": original["smiles"],
                "sas_score": original["sas_score"],
                "lipinski_pass": original["lipinski_pass"],
                "admet_scores": original["admet_scores"],
                "docking_score": docking_score,
                "combined_score": original["combined_score"],
            },
            "optimized": {
                "smiles": selected_variant["smiles"],
                "sas_score": selected_variant["sas_score"],
                "lipinski_pass": selected_variant["lipinski_pass"],
                "admet_scores": selected_variant["admet_scores"],
                "combined_score": selected_variant["combined_score"],
                "molecular_weight": selected_variant["molecular_weight"],
                "logp": selected_variant["logp"],
                "hbd": selected_variant["hbd"],
                "hba": selected_variant["hba"],
                "tpsa": selected_variant["tpsa"],
                "rotatable_bonds": selected_variant["rotatable_bonds"],
                "smiles_valid": selected_variant["smiles_valid"],
            },
            "changes": list(selected_variant.get("changes", [])),
            "strategy_used": selected_variant.get("strategy_used"),
            "optimization_quality": starting_quality,
            "optimization_note": optimization_note,
        }

    # FIXED
    @staticmethod
    async def optimize_best_available_for_target(target_id: str, db: Any) -> Dict[str, Any]:
        """Select the top-ranked docked molecules and optimize the best available starting point."""
        from app.models.molecule import Molecule

        molecules = db.query(Molecule).filter(Molecule.target_id == target_id).all()
        candidates = OptimizationService.select_candidates_for_optimization(molecules)
        if not candidates:
            raise ValueError("No docked molecules available for optimization")
        return await OptimizationService.optimize_molecule(str(candidates[0].id), db)

    # FIXED
    @staticmethod
    async def optimize_molecule(molecule_id: str, db: Any) -> Dict[str, Any]:
        """Optimize a stored molecule and persist the best-modified or fallback lead."""
        from app.models.molecule import Molecule

        molecule = db.query(Molecule).filter(Molecule.id == molecule_id).first()
        if not molecule:
            raise ValueError("Molecule not found")

        optimization_result = OptimizationService.optimize_smiles(molecule.smiles, docking_score=molecule.docking_score)
        optimized = optimization_result["optimized"]
        optimized_molecule = Molecule(
            target_id=molecule.target_id,
            smiles=optimized["smiles"],
            molecular_weight=optimized.get("molecular_weight"),
            logp=optimized.get("logp"),
            tpsa=optimized.get("tpsa"),
            rotatable_bonds=optimized.get("rotatable_bonds"),
            smiles_valid=optimized.get("smiles_valid", True),
            lipinski_pass=optimized["lipinski_pass"],
            sas_score=optimized["sas_score"],
            admet_scores=optimized["admet_scores"],
            docking_score=None,
            is_optimized=True,
            optimization_changes=list(optimization_result["changes"]),
        )

        db.add(optimized_molecule)
        db.commit()
        db.refresh(optimized_molecule)

        optimized["molecule_id"] = str(optimized_molecule.id)
        return optimization_result
