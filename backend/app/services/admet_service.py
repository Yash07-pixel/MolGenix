"""
ADMET Prediction Service - DeepChem and RDKit-based property prediction.

The heavy chemistry and ML dependencies are optional in local development.
When they are unavailable, the service falls back to coarse heuristics so the
API can still import and respond instead of crashing at startup.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from app.models.target_context import TargetContext

try:
    from rdkit import Chem
    from rdkit.Chem import Descriptors, rdMolDescriptors

    RDKIT_AVAILABLE = True
except ImportError:
    Chem = None
    Descriptors = None
    rdMolDescriptors = None
    RDKIT_AVAILABLE = False

try:
    import deepchem as dc

    DEEPCHEM_AVAILABLE = True
except ImportError:
    dc = None
    DEEPCHEM_AVAILABLE = False

logger = logging.getLogger(__name__)

if not RDKIT_AVAILABLE:
    logger.warning("RDKit not available - ADMET service using heuristic fallbacks")
if not DEEPCHEM_AVAILABLE:
    logger.warning("DeepChem not available - ADMET service using non-ML fallbacks")


class ADMETService:
    """Predict ADMET properties for molecules using DeepChem and RDKit."""

    _bbbp_model = None
    _toxicity_model = None
    _bbbp_attempted = False
    _toxicity_attempted = False
    _ecfp_featurizer = None

    @staticmethod
    def _clamp_score(value: Optional[float], *, floor: float = 0.01, ceiling: float = 0.99) -> Optional[float]:
        """Clamp floating scores to a stable probability-like range."""
        if value is None:
            return None
        return round(max(floor, min(ceiling, float(value))), 2)

    @staticmethod
    def _parse_molecule(smiles: str) -> Any:
        """Best-effort SMILES parsing with an RDKit-free fallback."""
        if not smiles or not isinstance(smiles, str):
            return None

        if not RDKIT_AVAILABLE:
            invalid_chars = {" ", "\t", "\n"}
            if any(char in smiles for char in invalid_chars):
                return None
            return smiles

        return Chem.MolFromSmiles(smiles)

    @staticmethod
    def _fallback_smiles_features(smiles: str) -> Dict[str, float]:
        """Coarse string-based features for environments without RDKit."""
        return {
            "length": float(len(smiles)),
            "hetero_atoms": float(sum(smiles.count(atom) for atom in ("N", "O", "S", "P"))),
            "aromatic_markers": float(smiles.count("c") + smiles.count("n")),
            "halogens": float(smiles.count("Cl") + smiles.count("Br") + smiles.count("F")),
            "ring_markers": float(sum(smiles.count(ch) for ch in "123456789")),
        }

    @staticmethod
    def _load_bbbp_model():
        """Load and cache a BBBP model built from DeepChem MolNet data."""
        if ADMETService._bbbp_model is not None or ADMETService._bbbp_attempted:
            return ADMETService._bbbp_model
        ADMETService._bbbp_attempted = True

        if not DEEPCHEM_AVAILABLE:
            logger.warning("DeepChem not available - BBBP prediction using fallback")
            return None

        try:
            logger.info("Loading BBBP model")
            _tasks, datasets, _transformers = dc.molnet.load_bbbp(featurizer="ECFP")
            X_train, y_train = ADMETService._get_labeled_training_data(datasets[0], 0)
            model = RandomForestClassifier(
                n_estimators=200,
                random_state=42,
                n_jobs=1,
                class_weight="balanced",
            )
            model.fit(X_train, y_train)
            ADMETService._bbbp_model = model
            logger.info("BBBP model loaded")
            return model
        except Exception as exc:
            logger.error(f"Failed to load BBBP model: {exc}")
            return None

    @staticmethod
    def _load_toxicity_model():
        """Load and cache a toxicity model from DeepChem MolNet data."""
        if ADMETService._toxicity_model is not None or ADMETService._toxicity_attempted:
            return ADMETService._toxicity_model
        ADMETService._toxicity_attempted = True

        if not DEEPCHEM_AVAILABLE:
            logger.warning("DeepChem not available - toxicity prediction using fallback")
            return None

        try:
            logger.info("Loading ClinTox model")
            tasks, datasets, _transformers = dc.molnet.load_clintox(featurizer="ECFP")
            toxicity_task_index = 1 if len(tasks) > 1 else 0
            X_train, y_train = ADMETService._get_labeled_training_data(datasets[0], toxicity_task_index)
            model = RandomForestClassifier(
                n_estimators=200,
                random_state=42,
                n_jobs=1,
                class_weight="balanced",
            )
            model.fit(X_train, y_train)
            ADMETService._toxicity_model = model
            logger.info("ClinTox model loaded")
            return model
        except Exception as exc:
            logger.error(f"Failed to load ClinTox model: {exc}")
            return None

    @staticmethod
    def _get_ecfp_featurizer():
        if not DEEPCHEM_AVAILABLE:
            return None
        if ADMETService._ecfp_featurizer is None:
            ADMETService._ecfp_featurizer = dc.feat.CircularFingerprint(size=1024)
        return ADMETService._ecfp_featurizer

    @staticmethod
    def _get_labeled_training_data(dataset: Any, task_index: int):
        labels = dataset.y[:, task_index]
        weights = dataset.w[:, task_index] if getattr(dataset, "w", None) is not None else np.ones_like(labels)
        mask = (weights > 0) & ~np.isnan(labels)
        return dataset.X[mask], labels[mask]

    @staticmethod
    def _featurize_smiles(smiles: str):
        featurizer = ADMETService._get_ecfp_featurizer()
        if featurizer is None:
            return None
        features = featurizer.featurize([smiles])
        if len(features) == 0:
            return None
        return features[0]

    @staticmethod
    def predict_bbbp(smiles: str) -> Optional[float]:
        """Predict blood-brain barrier penetration probability."""
        try:
            mol = ADMETService._parse_molecule(smiles)
            if mol is None:
                return None

            if DEEPCHEM_AVAILABLE and RDKIT_AVAILABLE:
                model = ADMETService._load_bbbp_model()
                if model is not None:
                    features = ADMETService._featurize_smiles(smiles)
                    if features is not None:
                        probabilities = model.predict_proba([features])
                        if len(probabilities) > 0:
                            return ADMETService._clamp_score(float(probabilities[0][1]))

            if RDKIT_AVAILABLE:
                mw = rdMolDescriptors.CalcExactMolWt(mol)
                logp = Descriptors.MolLogP(mol)
                tpsa = Descriptors.TPSA(mol)
                hbd = Descriptors.NumHDonors(mol)
                hba = Descriptors.NumHAcceptors(mol)

                score = 0.62
                score += min(0.18, max(-0.18, (logp - 2.1) * 0.08))
                score -= min(0.28, max(0.0, mw - 320.0) / 500.0)
                score -= min(0.30, max(0.0, tpsa - 60.0) / 180.0)
                score -= min(0.10, max(0, hbd - 1) * 0.05)
                score -= min(0.08, max(0, hba - 6) * 0.02)
                return ADMETService._clamp_score(score)

            features = ADMETService._fallback_smiles_features(smiles)
            score = 0.62
            score -= min(0.24, max(0.0, features["length"] - 45.0) / 140.0)
            score -= min(0.16, max(0.0, features["hetero_atoms"] - 5.0) * 0.03)
            score += min(0.10, features["halogens"] * 0.03)
            score -= min(0.14, features["ring_markers"] * 0.025)
            return ADMETService._clamp_score(score)
        except Exception as exc:
            logger.warning(f"BBBP prediction failed: {exc}")
            return None

    @staticmethod
    def predict_hepatotoxicity(smiles: str) -> Optional[float]:
        """Predict hepatotoxicity risk, where higher means more toxic."""
        try:
            mol = ADMETService._parse_molecule(smiles)
            if mol is None:
                return None

            if DEEPCHEM_AVAILABLE and RDKIT_AVAILABLE:
                model = ADMETService._load_toxicity_model()
                if model is not None:
                    features = ADMETService._featurize_smiles(smiles)
                    if features is not None:
                        probabilities = model.predict_proba([features])
                        if len(probabilities) > 0:
                            return ADMETService._clamp_score(float(probabilities[0][1]))

            if RDKIT_AVAILABLE:
                mw = rdMolDescriptors.CalcExactMolWt(mol)
                logp = Descriptors.MolLogP(mol)
                aromatic_rings = Descriptors.NumAromaticRings(mol)
                tpsa = Descriptors.TPSA(mol)
                hetero_atoms = rdMolDescriptors.CalcNumHeteroatoms(mol)

                risk = 0.16
                risk += min(0.22, max(0.0, logp - 2.5) * 0.09)
                risk += min(0.18, max(0.0, mw - 350.0) / 550.0)
                risk += min(0.16, max(0, aromatic_rings - 1) * 0.05)
                risk += min(0.12, max(0, hetero_atoms - 4) * 0.02)
                risk += min(0.10, max(0.0, tpsa - 110.0) / 250.0)
                return ADMETService._clamp_score(risk)

            features = ADMETService._fallback_smiles_features(smiles)
            risk = 0.18
            risk += min(0.20, max(0.0, features["length"] - 55.0) / 180.0)
            risk += min(0.18, max(0.0, features["aromatic_markers"] - 6.0) * 0.03)
            risk += min(0.12, features["halogens"] * 0.04)
            risk += min(0.10, max(0.0, features["hetero_atoms"] - 5.0) * 0.025)
            return ADMETService._clamp_score(risk)
        except Exception as exc:
            logger.warning(f"Hepatotoxicity prediction failed: {exc}")
            return None

    @staticmethod
    def predict_herg(smiles: str) -> Tuple[bool, float]:
        """Predict hERG cardiotoxicity risk."""
        try:
            mol = ADMETService._parse_molecule(smiles)
            if mol is None:
                return False, 0.0

            if RDKIT_AVAILABLE:
                mw = rdMolDescriptors.CalcExactMolWt(mol)
                logp = Descriptors.MolLogP(mol)
                risk_flag = mw > 500 and logp > 3
                confidence = 0.0
                if mw > 500:
                    confidence += 0.5
                if logp > 3:
                    confidence += 0.5
                return risk_flag, round(confidence, 2)

            features = ADMETService._fallback_smiles_features(smiles)
            risk_flag = features["length"] > 100 and features["aromatic_markers"] > 12
            return risk_flag, 0.7 if risk_flag else 0.2
        except Exception as exc:
            logger.warning(f"hERG prediction failed: {exc}")
            return False, 0.0

    @staticmethod
    def predict_oral_bioavailability(mol: Any, lipinski_pass: bool) -> float:
        """Predict oral bioavailability using rules or a coarse fallback."""
        try:
            score = 0.72 if lipinski_pass else 0.48

            if not RDKIT_AVAILABLE or mol is None:
                score += 0.05 if lipinski_pass else -0.05
                return ADMETService._clamp_score(score)

            mw = rdMolDescriptors.CalcExactMolWt(mol)
            logp = Descriptors.MolLogP(mol)
            num_rotatable = Descriptors.NumRotatableBonds(mol)
            tpsa = Descriptors.TPSA(mol)
            hbd = Descriptors.NumHDonors(mol)

            score -= min(0.18, max(0.0, mw - 350.0) / 500.0)
            score -= min(0.18, max(0.0, tpsa - 90.0) / 180.0)
            score -= min(0.16, max(0, num_rotatable - 5) * 0.025)
            score -= min(0.12, max(0.0, logp - 3.5) * 0.08)
            score -= min(0.10, max(0, hbd - 2) * 0.04)

            if mw <= 320:
                score += 0.03
            if 1.0 <= logp <= 3.5:
                score += 0.03
            if tpsa <= 100:
                score += 0.03

            return ADMETService._clamp_score(score)
        except Exception as exc:
            logger.warning(f"Bioavailability prediction failed: {exc}")
            return 0.01

    @staticmethod
    def predict_solubility(smiles: str) -> Optional[float]:
        """Predict aqueous solubility proxy where higher is better."""
        try:
            mol = ADMETService._parse_molecule(smiles)
            if mol is None:
                return None
            if not RDKIT_AVAILABLE:
                features = ADMETService._fallback_smiles_features(smiles)
                score = 0.7 - min(0.4, features["aromatic_markers"] * 0.02) - min(0.2, features["length"] / 200.0)
                return round(max(0.0, min(1.0, score)), 2)
            logp = Descriptors.MolLogP(mol)
            tpsa = Descriptors.TPSA(mol)
            score = 0.85 - max(0.0, logp - 2.0) * 0.12 + min(0.15, tpsa / 400.0)
            return round(max(0.0, min(1.0, score)), 2)
        except Exception as exc:
            logger.warning(f"Solubility prediction failed: {exc}")
            return None

    @staticmethod
    def predict_clearance(smiles: str) -> Optional[float]:
        """Predict metabolic stability proxy where higher is better."""
        try:
            mol = ADMETService._parse_molecule(smiles)
            if mol is None:
                return None
            if not RDKIT_AVAILABLE:
                features = ADMETService._fallback_smiles_features(smiles)
                score = 0.75 - min(0.3, features["hetero_atoms"] * 0.03) - min(0.15, features["halogens"] * 0.05)
                return round(max(0.0, min(1.0, score)), 2)
            mw = rdMolDescriptors.CalcExactMolWt(mol)
            rotatable = Descriptors.NumRotatableBonds(mol)
            score = 0.9 - max(0.0, mw - 350) / 600.0 - min(0.2, rotatable * 0.03)
            return round(max(0.0, min(1.0, score)), 2)
        except Exception as exc:
            logger.warning(f"Clearance prediction failed: {exc}")
            return None

    @staticmethod
    def predict_cyp3a4_liability(smiles: str) -> Optional[float]:
        """Predict CYP3A4 inhibition liability where lower is better."""
        try:
            mol = ADMETService._parse_molecule(smiles)
            if mol is None:
                return None
            if not RDKIT_AVAILABLE:
                features = ADMETService._fallback_smiles_features(smiles)
                risk = 0.2 + min(0.4, features["aromatic_markers"] * 0.03) + min(0.2, features["halogens"] * 0.06)
                return round(max(0.0, min(1.0, risk)), 2)
            logp = Descriptors.MolLogP(mol)
            aromatic_rings = Descriptors.NumAromaticRings(mol)
            risk = 0.1 + max(0.0, logp - 2.5) * 0.12 + min(0.3, aromatic_rings * 0.08)
            return round(max(0.0, min(1.0, risk)), 2)
        except Exception as exc:
            logger.warning(f"CYP3A4 liability prediction failed: {exc}")
            return None

    @staticmethod
    def classify_traffic_light(score: Optional[float], *, lower_is_better: bool = False) -> str:
        """Classify a score as green, yellow, red, or unknown."""
        if score is None:
            return "unknown"
        if lower_is_better:
            if score < 0.3:
                return "green"
            if score <= 0.6:
                return "yellow"
            return "red"
        if score > 0.7:
            return "green"
        if score >= 0.4:
            return "yellow"
        return "red"

    @staticmethod
    async def predict_admet_for_molecules(
        molecule_ids: List[str],
        db: Any,
    ) -> List[Dict[str, Any]]:
        """Predict ADMET properties for a list of molecules."""
        from app.models.molecule import Molecule

        results: List[Dict[str, Any]] = []

        for mol_id in molecule_ids:
            try:
                molecule = db.query(Molecule).filter(Molecule.id == mol_id).first()
                if not molecule:
                    logger.warning(f"Molecule {mol_id} not found")
                    continue

                parsed_mol = ADMETService._parse_molecule(molecule.smiles)
                if parsed_mol is None:
                    logger.warning(f"Invalid SMILES for {mol_id}: {molecule.smiles}")
                    continue

                bbbp_score = ADMETService.predict_bbbp(molecule.smiles)
                hepatotox_score = ADMETService.predict_hepatotoxicity(molecule.smiles)
                herg_risk, herg_confidence = ADMETService.predict_herg(molecule.smiles)
                bioavail_score = ADMETService.predict_oral_bioavailability(
                    parsed_mol if RDKIT_AVAILABLE else None,
                    molecule.lipinski_pass,
                )
                solubility_score = ADMETService.predict_solubility(molecule.smiles)
                clearance_score = ADMETService.predict_clearance(molecule.smiles)
                cyp3a4_liability = ADMETService.predict_cyp3a4_liability(molecule.smiles)

                existing_metadata = molecule.admet_scores if isinstance(molecule.admet_scores, dict) else {}
                admet_data = {
                    **existing_metadata,
                    "bbbp_score": bbbp_score,
                    "bbbp_traffic": ADMETService.classify_traffic_light(bbbp_score),
                    "hepatotoxicity_score": hepatotox_score,
                    "hepatotoxicity_traffic": ADMETService.classify_traffic_light(hepatotox_score, lower_is_better=True),
                    "herg_risk": herg_risk,
                    "herg_confidence": herg_confidence,
                    "bioavailability_score": bioavail_score,
                    "bioavailability_traffic": ADMETService.classify_traffic_light(bioavail_score),
                    "solubility_score": solubility_score,
                    "solubility_traffic": ADMETService.classify_traffic_light(solubility_score),
                    "clearance_score": clearance_score,
                    "clearance_traffic": ADMETService.classify_traffic_light(clearance_score),
                    "cyp3a4_liability": cyp3a4_liability,
                    "cyp3a4_traffic": ADMETService.classify_traffic_light(cyp3a4_liability, lower_is_better=True),
                    "model_source": "deepchem_hybrid" if DEEPCHEM_AVAILABLE else "rdkit_heuristic",
                }

                molecule.admet_scores = admet_data
                db.commit()

                results.append(
                    {
                        "molecule_id": str(mol_id),
                        "smiles": molecule.smiles,
                        "admet": admet_data,
                    }
                )
            except Exception as exc:
                logger.error(f"Failed to predict ADMET for {mol_id}: {exc}")
                db.rollback()
                continue

        return results

    @staticmethod
    async def score_molecules(
        target_context: TargetContext,
        molecules: List[Any],
        db: Any,
    ) -> List[Dict[str, Any]]:
        """Score molecules with ADMET while keeping a shared target context attached."""
        molecule_ids = [str(molecule.id) for molecule in molecules]
        results = await ADMETService.predict_admet_for_molecules(
            molecule_ids=molecule_ids,
            db=db,
        )

        for result in results:
            admet = result.get("admet", {})
            admet["target_context_id"] = target_context.target_id
            admet["target_gene_symbol"] = target_context.gene_symbol

        return results

    @staticmethod
    def get_summary(admet_data: Dict[str, Any]) -> Dict[str, str]:
        """Return a one-line traffic-light summary."""
        return {
            "bbbp": admet_data.get("bbbp_traffic", "unknown"),
            "hepatotoxicity": admet_data.get("hepatotoxicity_traffic", "unknown"),
            "herg": "red" if admet_data.get("herg_risk", False) else "green",
            "bioavailability": admet_data.get("bioavailability_traffic", "unknown"),
            "solubility": admet_data.get("solubility_traffic", "unknown"),
            "clearance": admet_data.get("clearance_traffic", "unknown"),
            "cyp3a4": admet_data.get("cyp3a4_traffic", "unknown"),
        }
