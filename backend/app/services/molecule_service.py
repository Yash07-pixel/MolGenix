"""
Molecule Generation Service - RDKit-based variant generation
"""
import asyncio
from contextlib import contextmanager
from dataclasses import dataclass, field
import logging
import random
import sys
import re
from typing import List, Dict, Any, Optional, Tuple
import httpx
from sqlalchemy.orm import Session
from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem, Descriptors, rdMolDescriptors
from rdkit.Chem import RDConfig

try:
    import sascorer
    SASCORER_AVAILABLE = True
except ImportError:
    try:
        sys.path.append(f"{RDConfig.RDContribDir}/SA_Score")
        import sascorer

        SASCORER_AVAILABLE = True
    except ImportError:
        sascorer = None
        SASCORER_AVAILABLE = False

from app.models.molecule import Molecule
from app.models.target import Target
from app.models.target_context import TargetContext
from app.config import settings

logger = logging.getLogger(__name__)

CHEMBL_TARGET_SEARCH_API = "https://www.ebi.ac.uk/chembl/api/data/target/search"

if not SASCORER_AVAILABLE:
    logger.warning("sascorer not available - using heuristic SAS fallback")

# Common drug-like fragments to add
FRAGMENT_LIBRARY = [
    'c1ccccc1',        # Benzene ring
    'C(=O)N',          # Amide
    'S(=O)(=O)N',      # Sulfonamide
    'C(F)(F)F',        # Trifluoromethyl
    'OC',              # Hydroxyl
    'NC(=O)',          # Urea
    'c1cc(C)ccc1',     # Toluene
    'c1ccc(O)cc1',     # Phenol
]

TARGET_CLASS_FALLBACK_SEEDS: Dict[str, Tuple[str, ...]] = {
    "kinase": (
        "c1ccc2[nH]ccc2c1",
        "Cc1ccc(NC(=O)c2ccc(CN3CCN(C)CC3)cc2)cc1Nc1nccc(-c2cccnc2)n1",
    ),
    "protease": (
        "CC(C)CC(NC(=O)OC(C)(C)C)C(=O)O",
        "O=C(O)c1ccccc1NC(=O)c1ccccc1",
    ),
    "cox": (
        "CCOc1ccc(-c2cc(=O)c3c(o2)-c2ccccc2OCC3)cc1",
        "O=C(O)c1ccc(Cl)cc1",
    ),
    "generic": (
        "c1ccc2c(c1)ccc(=O)o2",
        "CC(=O)Oc1ccccc1C(=O)O",
    ),
}


def build_target_profile(target_context: TargetContext) -> dict:
    # Determine target class from gene symbol or protein name
    name_lower = (target_context.protein_name + target_context.gene_symbol).lower()

    if any(x in name_lower for x in ["kinase", "egfr", "vegfr", "abl", "src"]):
        target_class = "kinase"
        mw_range = (300, 550)
        preferred_hbd = 3
        preferred_logp = (2, 5)
    elif any(x in name_lower for x in ["protease", "bace", "hiv", "thrombin", "factor"]):
        target_class = "protease"
        mw_range = (300, 600)
        preferred_hbd = 4
        preferred_logp = (1, 4)
    elif any(x in name_lower for x in ["cox", "cyclooxygenase", "ptgs"]):
        target_class = "cox"
        mw_range = (250, 500)
        preferred_hbd = 2
        preferred_logp = (3, 6)
    elif any(x in name_lower for x in ["gpcr", "receptor", "adrenergic", "dopamine"]):
        target_class = "gpcr"
        mw_range = (250, 500)
        preferred_hbd = 2
        preferred_logp = (2, 5)
    else:
        target_class = "generic"
        mw_range = (200, 500)
        preferred_hbd = 5
        preferred_logp = (0, 5)

    target_context.target_class = target_class
    return {
        "target_class": target_class,
        "mw_range": mw_range,
        "preferred_hbd": preferred_hbd,
        "preferred_logp": preferred_logp,
    }


@dataclass(frozen=True)
class TargetGenerationProfile:
    """Compact target-aware generation policy for seed-based design."""

    key: str
    inhibitor_type: str
    aliases: Tuple[str, ...]
    preferred_mw: Tuple[float, float]
    max_logp: float
    min_aromatic_rings: int
    min_hbd: int
    min_hba: int
    max_rotatable_bonds: int
    min_quick_binding_score: float
    scaffold_smiles: Tuple[str, ...] = field(default_factory=tuple)
    preferred_fragments: Tuple[str, ...] = field(default_factory=tuple)


TARGET_GENERATION_PROFILES: Tuple[TargetGenerationProfile, ...] = (
    TargetGenerationProfile(
        key="EGFR",
        inhibitor_type="kinase hinge-binding aromatic inhibitor",
        aliases=("egfr", "epidermal growth factor receptor", "erbb1", "her1"),
        preferred_mw=(300.0, 540.0),
        max_logp=5.5,
        min_aromatic_rings=2,
        min_hbd=0,
        min_hba=4,
        max_rotatable_bonds=10,
        min_quick_binding_score=-7.0,
        scaffold_smiles=(
            "COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1OCCCN1CCOCC1",
            "COCCOc1cc2ncnc(Nc3cccc(Cl)c3)c2cc1OCCOC",
            "COc1cc2ncnc(Nc3ccc(Br)cc3)c2cc1OCCN1CCOCC1",
            "COc1cc2ncnc(Nc3ccc(F)cc3)c2cc1OCCN1CCOCC1",
        ),
        preferred_fragments=("c1cc2ncncc2cc1", "c1ccc(F)c(Cl)c1", "N1CCOCC1", "OCCN"),
    ),
    TargetGenerationProfile(
        key="BACE1",
        inhibitor_type="aspartyl protease peptidomimetic with H-bond rich amines",
        aliases=("bace1", "beta-secretase", "beta secretase", "memapsin", "p56817"),
        preferred_mw=(320.0, 560.0),
        max_logp=4.8,
        min_aromatic_rings=1,
        min_hbd=2,
        min_hba=4,
        max_rotatable_bonds=13,
        min_quick_binding_score=-7.0,
        scaffold_smiles=(
            "CC(C)C(NC(=O)C(N)Cc1ccccc1)C(=O)NCC(O)CN",
            "NCC(O)CNC(=O)C(Cc1ccccc1)NC(=O)C(C)N",
            "CC(C)C(N)C(=O)NC(CO)C(O)CNC(=O)c1ccccc1",
            "NC(CO)C(O)CNC(=O)C(Cc1ccccc1)NC(=O)C(C)C",
        ),
        preferred_fragments=("NCC(O)CN", "C(=O)N", "NC(=O)", "Cc1ccccc1"),
    ),
)

REACTIVE_GROUP_SMARTS: Tuple[Tuple[str, str], ...] = (
    ("thioester", "[CX3](=[OX1])[SX2]"),
    ("acid_chloride", "[CX3](=[OX1])Cl"),
    ("isocyanate", "N=C=O"),
    ("isothiocyanate", "N=C=S"),
    ("azide", "[N-]=[N+]=N"),
    ("aldehyde", "[CX3H1](=O)[#6]"),
    ("anhydride", "[CX3](=O)O[CX3](=O)"),
    ("epoxide", "C1OC1"),
)

# Atom substitution patterns (original → replacements)
ATOM_SUBSTITUTIONS = {
    'C': ['N', 'O', 'S'],
    'N': ['C', 'O'],
    'O': ['N', 'S'],
}

TERMINAL_ATOM_SUBSTITUTIONS = {
    9: [17],
    17: [9, 35],
    35: [17],
    8: [7, 9],
    7: [8],
    6: [7, 9],
    16: [8],
}


class MoleculeGenerationService:
    """Generate drug-like molecules from seed SMILES using RDKit."""

    LIBRARY_MW_SOFT_MAX = 540.0
    LIBRARY_LOGP_SOFT_MAX = 6.2
    MIN_LIPINSKI_PASS_COUNT = 5

    @staticmethod
    @contextmanager
    def _suppress_rdkit_warnings():
        RDLogger.DisableLog('rdApp.*')
        try:
            yield
        finally:
            RDLogger.EnableLog('rdApp.*')

    @staticmethod
    def _infer_gene_symbol(target_name: str) -> str:
        tokens = re.findall(r"[A-Za-z0-9\-]+", target_name or "")
        if not tokens:
            return ""
        preferred = tokens[0].upper()
        alias_map = {
            "EPIDERMAL": "EGFR",
            "BETA": "BACE1",
            "CYCLOOXYGENASE": "COX-2",
        }
        return alias_map.get(preferred, preferred)

    @staticmethod
    def _profile_for_target(target: Target) -> Optional[TargetGenerationProfile]:
        """Infer a target-specific generation profile from stored target metadata."""
        target_text = " ".join(
            str(value or "")
            for value in (
                getattr(target, "name", None),
                getattr(target, "uniprot_id", None),
                getattr(target, "chembl_id", None),
                getattr(target, "known_inhibitors", None),
            )
        ).lower()
        for profile in TARGET_GENERATION_PROFILES:
            if any(alias in target_text for alias in profile.aliases):
                return profile
        return None

    @staticmethod
    def _profile_for_target_context(target_context: TargetContext) -> Optional[TargetGenerationProfile]:
        """Build a dynamic target-aware profile from a shared target context."""
        profile = build_target_profile(target_context)
        target_class = profile["target_class"]
        mw_low, mw_high = profile["mw_range"]
        logp_low, logp_high = profile["preferred_logp"]
        inhibitor_type_map = {
            "kinase": "kinase-focused small molecule",
            "protease": "protease-focused inhibitor",
            "cox": "cyclooxygenase-focused inhibitor",
            "gpcr": "gpcr-focused ligand",
            "generic": "generic drug-like ligand",
        }
        min_hba = max(2, profile["preferred_hbd"] + 1)
        min_aromatic = 2 if target_class in {"kinase", "cox", "gpcr"} else 1
        max_rotatable = 10 if target_class in {"kinase", "gpcr", "generic"} else 12
        min_quick_binding = -6.8 if target_class in {"kinase", "protease", "cox"} else -6.0
        return TargetGenerationProfile(
            key=target_class.upper(),
            inhibitor_type=inhibitor_type_map.get(target_class, "generic drug-like ligand"),
            aliases=(target_context.gene_symbol.lower(), target_context.protein_name.lower()),
            preferred_mw=(float(mw_low), float(mw_high)),
            max_logp=float(logp_high),
            min_aromatic_rings=min_aromatic,
            min_hbd=int(profile["preferred_hbd"]),
            min_hba=min_hba,
            max_rotatable_bonds=max_rotatable,
            min_quick_binding_score=min_quick_binding,
            preferred_fragments=TARGET_CLASS_FALLBACK_SEEDS.get(target_class, TARGET_CLASS_FALLBACK_SEEDS["generic"]),
        )

    @staticmethod
    def _descriptor_bundle(mol: Chem.Mol) -> Dict[str, Any]:
        """Return target-screening descriptors used before expensive docking."""
        return {
            **MoleculeGenerationService.calculate_lipinski_descriptors(mol),
            "aromatic_rings": int(rdMolDescriptors.CalcNumAromaticRings(mol)),
            "rotatable_bonds": int(Descriptors.NumRotatableBonds(mol)),
            "tpsa": round(float(Descriptors.TPSA(mol)), 2),
            "heavy_atoms": int(mol.GetNumHeavyAtoms()),
        }

    @staticmethod
    def compute_properties_from_smiles(smiles: str) -> Dict[str, Any]:
        """
        Computes molecular properties from SMILES using RDKit.
        Returns dict with mw, logp, hbd, hba, tpsa, rotatable_bonds.
        Returns None values if SMILES is invalid.
        """
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return {
                    "mw": None,
                    "logp": None,
                    "hbd": None,
                    "hba": None,
                    "tpsa": None,
                    "rotatable_bonds": None,
                    "smiles_valid": False,
                }
            return {
                "mw": round(float(Descriptors.MolWt(mol)), 2),
                "logp": round(float(Descriptors.MolLogP(mol)), 2),
                "hbd": int(Descriptors.NumHDonors(mol)),
                "hba": int(Descriptors.NumHAcceptors(mol)),
                "tpsa": round(float(Descriptors.TPSA(mol)), 2),
                "rotatable_bonds": int(Descriptors.NumRotatableBonds(mol)),
                "smiles_valid": True,
            }
        except Exception as exc:
            logger.warning("RDKit property computation failed for %s: %s", smiles, exc)
            return {
                "mw": None,
                "logp": None,
                "hbd": None,
                "hba": None,
                "tpsa": None,
                "rotatable_bonds": None,
                "smiles_valid": False,
            }

    @staticmethod
    def _reactive_group_hits(mol: Chem.Mol) -> List[str]:
        """Return unstable or toxicophore-like groups that should not enter docking."""
        hits: List[str] = []
        for label, smarts in REACTIVE_GROUP_SMARTS:
            pattern = Chem.MolFromSmarts(smarts)
            if pattern is not None and mol.HasSubstructMatch(pattern):
                hits.append(label)
        return hits

    @staticmethod
    def _quick_binding_score(mol: Chem.Mol, profile: Optional[TargetGenerationProfile]) -> float:
        """Cheap target-aware binding proxy used to reject weak candidates early."""
        descriptors = MoleculeGenerationService._descriptor_bundle(mol)
        mw = float(descriptors["molecular_weight"])
        logp = float(descriptors["logp"])
        hbd = int(descriptors["hbd"])
        hba = int(descriptors["hba"])
        aromatic = int(descriptors["aromatic_rings"])
        rotatable = int(descriptors["rotatable_bonds"])

        score = -4.0
        score -= min(aromatic, 4) * 0.75
        score -= min(hba, 8) * 0.22
        score -= min(hbd, 4) * 0.25
        score += max(0, rotatable - 8) * 0.12
        score += max(0.0, logp - 4.2) * 0.25

        if profile is not None:
            low_mw, high_mw = profile.preferred_mw
            if low_mw <= mw <= high_mw:
                score -= 0.8
            else:
                score += min(abs(mw - low_mw), abs(mw - high_mw)) / 220.0

            feature_matches = sum(
                [
                    aromatic >= profile.min_aromatic_rings,
                    hbd >= profile.min_hbd,
                    hba >= profile.min_hba,
                    rotatable <= profile.max_rotatable_bonds,
                    logp <= profile.max_logp,
                ]
            )
            score -= feature_matches * 0.35

            if profile.key == "EGFR":
                score -= 0.8 if aromatic >= 3 and hba >= 5 else 0.0
            elif profile.key == "BACE1":
                score -= 0.8 if hbd >= 2 and hba >= 5 and descriptors["tpsa"] >= 80 else 0.0

        return round(max(-12.0, min(-2.0, score)), 2)

    @staticmethod
    def _passes_target_prefilter(
        mol: Chem.Mol,
        profile: Optional[TargetGenerationProfile],
    ) -> Tuple[bool, Dict[str, Any]]:
        """Apply proactive ADMET, pharmacophore, and quick-binding filters."""
        descriptors = MoleculeGenerationService._descriptor_bundle(mol)
        reasons: List[str] = []
        reactive_hits = MoleculeGenerationService._reactive_group_hits(mol)
        if reactive_hits:
            reasons.append(f"reactive_groups:{','.join(reactive_hits)}")

        if profile is not None:
            low_mw, high_mw = profile.preferred_mw
            mw = float(descriptors["molecular_weight"])
            if mw < low_mw or mw > high_mw:
                reasons.append("target_mw_range")
            if float(descriptors["logp"]) > profile.max_logp:
                reasons.append("target_logp")
            if int(descriptors["aromatic_rings"]) < profile.min_aromatic_rings:
                reasons.append("target_aromatic_pharmacophore")
            if int(descriptors["hbd"]) < profile.min_hbd:
                reasons.append("target_hbd_pharmacophore")
            if int(descriptors["hba"]) < profile.min_hba:
                reasons.append("target_hba_pharmacophore")
            if int(descriptors["rotatable_bonds"]) > profile.max_rotatable_bonds:
                reasons.append("target_flexibility")

        quick_score = MoleculeGenerationService._quick_binding_score(mol, profile)
        threshold = profile.min_quick_binding_score if profile is not None else -6.0
        if quick_score > threshold:
            reasons.append("weak_quick_binding_score")

        return not reasons, {
            **descriptors,
            "quick_binding_score": quick_score,
            "target_profile": profile.key if profile else "generic",
            "inhibitor_type": profile.inhibitor_type if profile else "generic drug-like ligand",
            "prefilter_reasons": reasons,
        }

    @staticmethod
    def _sanitize_smiles(smiles: str) -> tuple[Optional[Chem.Mol], Optional[str]]:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            logger.warning("Invalid SMILES skipped: %s", smiles)
            return None, None

        try:
            Chem.SanitizeMol(mol)
        except Exception as exc:
            logger.warning("Unsanitizable SMILES skipped: %s (%s)", smiles, exc)
            return None, None

        canonical_smiles = Chem.MolToSmiles(mol)
        if not canonical_smiles:
            logger.warning("Canonicalization failed for SMILES: %s", smiles)
            return None, None

        return mol, canonical_smiles

    @staticmethod
    def _candidate_priority(molecule: Molecule) -> tuple[float, float, float, int]:
        """Rank molecules with a bias toward Lipinski compliance and tractability."""
        metadata = molecule.admet_scores if isinstance(molecule.admet_scores, dict) else {}
        mw = float(metadata.get("molecular_weight", 9999) or 9999)
        logp = float(metadata.get("logp", 99) or 99)
        violations = int(metadata.get("lipinski_violations", 99) or 99)
        return (
            0.0 if molecule.lipinski_pass else 1.0,
            0.0 if violations == 0 else 1.0,
            violations,
            molecule.sas_score if molecule.sas_score is not None else 10.0,
            abs(logp - 2.5),
            int(mw),
        )

    @staticmethod
    def _library_quality_filter(molecule: Molecule) -> bool:
        """Exclude clearly unsuitable library compounds before downstream scoring."""
        metadata = molecule.admet_scores if isinstance(molecule.admet_scores, dict) else {}
        mw = float(metadata.get("molecular_weight", 9999) or 9999)
        logp = float(metadata.get("logp", 99) or 99)
        hbd = int(metadata.get("hbd", 99) or 99)
        hba = int(metadata.get("hba", 99) or 99)

        return (
            mw <= MoleculeGenerationService.LIBRARY_MW_SOFT_MAX
            and logp <= MoleculeGenerationService.LIBRARY_LOGP_SOFT_MAX
            and hbd <= 7
            and hba <= 12
        )

    @staticmethod
    def _build_molecule_record(
        target_id: str,
        smiles: str,
        source: Optional[str] = None,
        source_id: Optional[str] = None,
        computed_properties: Optional[Dict[str, Any]] = None,
        target_profile: Optional[TargetGenerationProfile] = None,
        require_target_prefilter: bool = False,
        max_lipinski_violations: int = 2,
        enforce_reactive_filter: bool = True,
    ) -> Optional[Molecule]:
        """Create a scored Molecule ORM object from a SMILES string."""
        mol, canonical_smiles = MoleculeGenerationService._sanitize_smiles(smiles)
        if mol is None or canonical_smiles is None:
            return None

        rdkit_properties = computed_properties or MoleculeGenerationService.compute_properties_from_smiles(canonical_smiles)
        if not rdkit_properties.get("smiles_valid"):
            logger.warning("Skipping molecule with invalid SMILES after sanitization: %s", canonical_smiles)
            return None

        lipinski_data = MoleculeGenerationService.calculate_lipinski_descriptors(mol, rdkit_properties)
        if lipinski_data["lipinski_violations"] > max_lipinski_violations:
            logger.info(
                "Discarding non-Lipinski molecule %s (violations=%s)",
                canonical_smiles,
                lipinski_data["lipinski_violations"],
            )
            return None
        sas = MoleculeGenerationService.calculate_sas_score(mol)

        prefilter_pass, target_metadata = MoleculeGenerationService._passes_target_prefilter(mol, target_profile)
        has_reactive_group = any(
            reason.startswith("reactive_groups:")
            for reason in target_metadata.get("prefilter_reasons", [])
        )
        if (enforce_reactive_filter and has_reactive_group) or (require_target_prefilter and not prefilter_pass):
            logger.info(
                "Discarding %s for target profile %s: %s",
                canonical_smiles,
                target_metadata.get("target_profile"),
                target_metadata.get("prefilter_reasons"),
            )
            return None

        admet_scores = {
            'molecular_weight': lipinski_data['molecular_weight'],
            'hbd': lipinski_data['hbd'],
            'hba': lipinski_data['hba'],
            'logp': lipinski_data['logp'],
            'tpsa': rdkit_properties['tpsa'],
            'rotatable_bonds': rdkit_properties['rotatable_bonds'],
            'smiles_valid': rdkit_properties['smiles_valid'],
            'lipinski_violations': lipinski_data['lipinski_violations'],
            **target_metadata,
        }
        if source:
            admet_scores['library_source'] = source
        if source_id:
            admet_scores['library_source_id'] = source_id

        return Molecule(
            target_id=target_id,
            smiles=canonical_smiles,
            molecular_weight=lipinski_data['molecular_weight'],
            logp=lipinski_data['logp'],
            tpsa=rdkit_properties['tpsa'],
            rotatable_bonds=rdkit_properties['rotatable_bonds'],
            smiles_valid=bool(rdkit_properties['smiles_valid']),
            lipinski_pass=lipinski_data['lipinski_pass'],
            sas_score=sas,
            admet_scores=admet_scores,
        )

    @staticmethod
    def _persist_unique_molecules(target_id: str, db: Session, molecules: List[Molecule]) -> Tuple[List[Molecule], int]:
        """Persist only new SMILES for a target and return saved molecules plus Lipinski pass count."""
        saved_molecules, lipinski_pass_count, _existing_count = MoleculeGenerationService._persist_candidates(
            target_id,
            db,
            molecules,
            require_lipinski_pass=True,
        )
        return saved_molecules, lipinski_pass_count

    @staticmethod
    def _persist_candidates(
        target_id: str,
        db: Session,
        molecules: List[Molecule],
        *,
        require_lipinski_pass: bool,
    ) -> Tuple[List[Molecule], int, int]:
        """Persist new candidate molecules and report Lipinski-pass and duplicate counts."""
        if not molecules:
            return [], 0, 0

        existing_smiles = {
            row[0]
            for row in db.query(Molecule.smiles).filter(Molecule.target_id == target_id).all()
        }

        unique_molecules: List[Molecule] = []
        seen_smiles = set()
        lipinski_pass_count = 0
        already_existing_count = 0

        for molecule in molecules:
            if require_lipinski_pass and not molecule.lipinski_pass:
                continue
            if molecule.smiles in existing_smiles:
                already_existing_count += 1
                continue
            if molecule.smiles in seen_smiles:
                continue

            seen_smiles.add(molecule.smiles)
            unique_molecules.append(molecule)
            if molecule.lipinski_pass:
                lipinski_pass_count += 1

        for molecule in unique_molecules:
            db.add(molecule)

        db.commit()
        logger.info(
            "Saved %s molecules (%s passed Lipinski) for target %s",
            len(unique_molecules),
            lipinski_pass_count,
            target_id,
        )
        return unique_molecules, lipinski_pass_count, already_existing_count

    @staticmethod
    def _sort_candidates(molecules: List[Molecule]) -> List[Molecule]:
        """Return molecules sorted by the internal desirability heuristic."""
        return sorted(molecules, key=MoleculeGenerationService._candidate_priority)

    @staticmethod
    def _select_best_library_molecules(molecules: List[Molecule], desired_count: int) -> List[Molecule]:
        """Return the best sanitized, Lipinski-passing library candidates only."""
        filtered = [molecule for molecule in molecules if MoleculeGenerationService._library_quality_filter(molecule)]
        ranked = MoleculeGenerationService._sort_candidates(filtered or molecules)
        lipinski_passers = [molecule for molecule in ranked if molecule.lipinski_pass]
        return lipinski_passers[:desired_count]

    @staticmethod
    async def _fetch_activity_rows_for_target(
        client: httpx.AsyncClient,
        activity_url: str,
        target_chembl_id: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Fetch activity rows for a single ChEMBL target ID."""
        activities: List[Dict[str, Any]] = []
        activity_queries = [
            {
                "target_chembl_id": target_chembl_id,
                "limit": max(200, limit),
                "molecule_type": "Small Molecule",
                "standard_type": "IC50",
                "pchembl_value__isnull": False,
                "sort": "-pchembl_value",
            },
            {
                "target_chembl_id": target_chembl_id,
                "limit": max(200, limit),
                "molecule_type": "Small Molecule",
                "standard_type": "Ki",
                "pchembl_value__isnull": False,
                "sort": "-pchembl_value",
            },
            {
                "target_chembl_id": target_chembl_id,
                "limit": max(200, limit),
                "molecule_type": "Small Molecule",
                "standard_type": "IC50",
                "standard_value__isnull": False,
            },
            {
                "target_chembl_id": target_chembl_id,
                "limit": max(200, limit),
                "molecule_type": "Small Molecule",
                "standard_type": "Ki",
                "standard_value__isnull": False,
            },
            {
                "target_chembl_id": target_chembl_id,
                "limit": max(200, limit),
                "molecule_type": "Small Molecule",
            },
        ]

        for params in activity_queries:
            response = await client.get(activity_url, params=params)
            response.raise_for_status()
            activities = response.json().get("activities", [])
            if activities:
                break

        logger.info("ChEMBL activity query for %s returned %s rows", target_chembl_id, len(activities))
        return activities

    @staticmethod
    def _activity_molecular_weight(activity: Dict[str, Any]) -> Optional[float]:
        """Return an activity row molecular weight when ChEMBL exposes it."""
        properties = activity.get("molecule_properties")
        candidates: List[Any] = []
        if isinstance(properties, dict):
            candidates.extend(
                [
                    properties.get("full_mwt"),
                    properties.get("mw_freebase"),
                    properties.get("molecular_weight"),
                ]
            )
        candidates.extend(
            [
                activity.get("mw_freebase"),
                activity.get("full_mwt"),
                activity.get("molecular_weight"),
            ]
        )
        for value in candidates:
            try:
                if value not in (None, ""):
                    return float(value)
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    async def _lookup_fallback_chembl_target_ids(client: httpx.AsyncClient, gene_symbol: str, limit: int = 3) -> List[str]:
        """Query ChEMBL target search and return the top candidate target IDs for a gene symbol."""
        if not gene_symbol:
            return []

        response = await client.get(
            CHEMBL_TARGET_SEARCH_API,
            params={"q": gene_symbol, "format": "json"},
        )
        response.raise_for_status()
        targets = response.json().get("targets", [])

        target_ids: List[str] = []
        for candidate in targets:
            target_id = candidate.get("target_chembl_id") or candidate.get("chembl_id")
            if not target_id or target_id in target_ids:
                continue
            target_ids.append(target_id)
            if len(target_ids) >= limit:
                break

        return target_ids

    @staticmethod
    async def _fetch_chembl_activity_molecules(
        target_chembl_id: str,
        gene_symbol: str,
        limit: int,
        allow_target_fallback_ids: bool = True,
    ) -> List[Dict[str, str]]:
        """Fetch distinct active compounds for a ChEMBL target with a low-signal fallback search."""
        activity_url = f"{settings.CHEMBL_API_BASE}/activity.json"
        molecule_base_url = f"{settings.CHEMBL_API_BASE}/molecule"

        async with httpx.AsyncClient(timeout=30.0) as client:
            target_ids = [target_chembl_id]
            primary_activities = await MoleculeGenerationService._fetch_activity_rows_for_target(
                client,
                activity_url,
                target_chembl_id,
                limit,
            )
            combined_activities = list(primary_activities)
            if allow_target_fallback_ids and len(primary_activities) < 10:
                fallback_ids = await MoleculeGenerationService._lookup_fallback_chembl_target_ids(client, gene_symbol)
                for fallback_id in fallback_ids:
                    if fallback_id in target_ids:
                        continue
                    target_ids.append(fallback_id)

                if target_ids[1:]:
                    fallback_results = await asyncio.gather(
                        *(
                            MoleculeGenerationService._fetch_activity_rows_for_target(client, activity_url, fallback_id, limit)
                            for fallback_id in target_ids[1:]
                        )
                    )
                    for rows in fallback_results:
                        combined_activities.extend(rows)

            seen_activity_ids = set()
            activities = []
            for activity in combined_activities:
                molecule_chembl_id = activity.get("molecule_chembl_id")
                if not molecule_chembl_id or molecule_chembl_id in seen_activity_ids:
                    continue
                seen_activity_ids.add(molecule_chembl_id)
                activities.append(activity)

            ordered_ids = []
            seen_ids = set()
            for activity in activities:
                molecule_chembl_id = activity.get("molecule_chembl_id")
                if not molecule_chembl_id or molecule_chembl_id in seen_ids:
                    continue
                activity_mw = MoleculeGenerationService._activity_molecular_weight(activity)
                if activity_mw is not None and activity_mw > 500:
                    logger.info(
                        "Skipping ChEMBL molecule %s before detail fetch: MW=%.1f",
                        molecule_chembl_id,
                        activity_mw,
                    )
                    continue
                seen_ids.add(molecule_chembl_id)
                ordered_ids.append(molecule_chembl_id)
                if len(ordered_ids) >= limit * 3:
                    break

            async def fetch_molecule(molecule_chembl_id: str) -> Optional[Dict[str, Any]]:
                molecule_response = await client.get(f"{molecule_base_url}/{molecule_chembl_id}.json")
                molecule_response.raise_for_status()
                molecule_data = molecule_response.json()
                smiles = (molecule_data.get("molecule_structures") or {}).get("canonical_smiles")
                if not smiles:
                    return None

                computed_properties = MoleculeGenerationService.compute_properties_from_smiles(smiles)
                if not computed_properties["smiles_valid"]:
                    logger.warning("Skipping ChEMBL molecule %s due to invalid SMILES", molecule_chembl_id)
                    return None

                molecule_properties = molecule_data.get("molecule_properties") or {}
                molecular_weight = computed_properties["mw"]
                if molecular_weight is None:
                    molecular_weight = (
                        molecule_properties.get("full_mwt")
                        or molecule_properties.get("mw_freebase")
                        or molecule_properties.get("molecular_weight")
                    )
                try:
                    if molecular_weight not in (None, "") and float(molecular_weight) > 500:
                        logger.info(
                            "Skipping ChEMBL detail %s after fetch: MW=%.1f",
                            molecule_chembl_id,
                            float(molecular_weight),
                        )
                        return None
                except (TypeError, ValueError):
                    pass
                return {
                    "chembl_id": molecule_chembl_id,
                    "smiles": smiles,
                    "pref_name": molecule_data.get("pref_name") or "",
                    "computed_properties": computed_properties,
                }

            molecule_results = await asyncio.gather(
                *(fetch_molecule(molecule_chembl_id) for molecule_chembl_id in ordered_ids),
                return_exceptions=True,
            )

        compounds: List[Dict[str, str]] = []
        for item in molecule_results:
            if isinstance(item, Exception):
                logger.warning("ChEMBL molecule lookup failed: %s", item)
                continue
            if item:
                compounds.append(item)
            if len(compounds) >= limit:
                break

        return compounds

    @staticmethod
    def _expand_seed_compounds(compounds: List[Dict[str, str]], desired_count: int) -> List[Dict[str, str]]:
        """Generate extra analogs from fetched ChEMBL hits when the library is sparse."""
        if desired_count <= 0:
            return []

        expanded: List[Dict[str, str]] = []
        seen_smiles = {compound["smiles"] for compound in compounds if compound.get("smiles")}
        seeds, _all_high_mw = MoleculeGenerationService._collect_analog_generation_seeds(compounds)
        if not seeds:
            return expanded

        if len(seeds) < 3:
            logger.info("Insufficient drug-like seeds for analog generation, using direct ChEMBL actives only")
            return expanded

        variants_per_seed = max(4, desired_count // max(1, len(seeds)))
        for seed in seeds:
            try:
                variants = MoleculeGenerationService.generate_variants(seed["smiles"], variants_per_seed)
            except Exception as exc:
                logger.warning("Analog expansion failed for %s: %s", seed.get("chembl_id") or seed.get("pref_name") or "seed", exc)
                continue

            for index, variant_smiles in enumerate(variants, start=1):
                if not variant_smiles or variant_smiles in seen_smiles:
                    continue
                mol, sanitized_smiles = MoleculeGenerationService._sanitize_smiles(variant_smiles)
                if mol is None or sanitized_smiles is None or sanitized_smiles in seen_smiles:
                    continue
                lipinski_data = MoleculeGenerationService.calculate_lipinski_descriptors(mol)
                if not lipinski_data["lipinski_pass"]:
                    continue
                seen_smiles.add(sanitized_smiles)
                expanded.append(
                    {
                        "chembl_id": seed.get("chembl_id"),
                        "smiles": sanitized_smiles,
                        "pref_name": seed.get("pref_name") or "",
                        "source": "chembl_seed_expanded",
                        "parent_smiles": seed["smiles"],
                        "variant_index": index,
                    }
                )
                if len(expanded) >= desired_count:
                    return expanded

        return expanded

    @staticmethod
    def _collect_analog_generation_seeds(
        compounds: List[Dict[str, str]],
    ) -> Tuple[List[Dict[str, str]], bool]:
        """Identify expansion seeds and report whether all sanitized compounds exceeded the MW ceiling."""
        seeds: List[Dict[str, str]] = []
        considered_compounds = 0
        high_mw_skips = 0

        for compound in compounds:
            smiles = compound.get("smiles")
            if not smiles:
                continue
            seed_mol, _ = MoleculeGenerationService._sanitize_smiles(smiles)
            if seed_mol is None:
                continue

            considered_compounds += 1
            molecular_weight = float(Descriptors.MolWt(seed_mol))
            if molecular_weight > 400:
                high_mw_skips += 1
                logger.info(
                    "Skipping seed %s: MW=%.1f too large for analog generation",
                    compound.get("chembl_id") or "unknown",
                    molecular_weight,
                )
                continue

            aromatic_rings = int(rdMolDescriptors.CalcNumAromaticRings(seed_mol))
            rotatable_bonds = int(Descriptors.NumRotatableBonds(seed_mol))
            if 200 <= molecular_weight <= 400 and aromatic_rings >= 1 and rotatable_bonds < 8:
                seeds.append(compound)

        return seeds, considered_compounds > 0 and high_mw_skips == considered_compounds

    @staticmethod
    def _build_direct_chembl_candidates(
        target_id: str,
        compounds: List[Dict[str, str]],
        *,
        max_lipinski_violations: int,
        limit: Optional[int] = None,
        source_label: str,
    ) -> List[Molecule]:
        """Create fallback candidates from direct ChEMBL actives without target-profile gating."""
        candidates: List[Molecule] = []

        for compound in compounds:
            molecule = MoleculeGenerationService._build_molecule_record(
                target_id=target_id,
                smiles=compound["smiles"],
                source=source_label,
                source_id=compound.get("chembl_id"),
                computed_properties=compound.get("computed_properties"),
                max_lipinski_violations=max_lipinski_violations,
                enforce_reactive_filter=False,
            )
            if molecule is None:
                continue
            candidates.append(molecule)
            if limit is not None and len(candidates) >= limit:
                break

        return candidates

    @staticmethod
    def _emergency_fallback_smiles(target_class: str) -> Tuple[str, ...]:
        """Return emergency seed SMILES when ChEMBL produces no viable small molecules."""
        return TARGET_CLASS_FALLBACK_SEEDS.get(target_class, TARGET_CLASS_FALLBACK_SEEDS["generic"])

    @staticmethod
    def _build_emergency_fallback_candidates(
        target_id: str,
        target_class: str,
        target_profile: Optional[TargetGenerationProfile],
        desired_count: int,
    ) -> List[Molecule]:
        """Generate emergency fallback analogs from a tiny curated seed library."""
        candidates: List[Molecule] = []
        seen_smiles: set[str] = set()
        seeds = MoleculeGenerationService._emergency_fallback_smiles(target_class)

        for seed_smiles in seeds:
            try:
                variants = MoleculeGenerationService.generate_target_aware_variants(
                    seed_smiles,
                    max(desired_count * 2, 8),
                    target_profile,
                )
            except Exception:
                try:
                    variants = MoleculeGenerationService.generate_variants(seed_smiles, max(desired_count * 2, 8))
                except Exception as exc:
                    logger.warning("Emergency fallback generation failed for seed %s: %s", seed_smiles, exc)
                    continue

            seed_and_variants = [seed_smiles, *variants]
            for smiles in seed_and_variants:
                molecule = MoleculeGenerationService._build_molecule_record(
                    target_id=target_id,
                    smiles=smiles,
                    source="emergency_seed_generated",
                    target_profile=target_profile,
                    require_target_prefilter=False,
                    max_lipinski_violations=2,
                    enforce_reactive_filter=True,
                )
                if molecule is None or molecule.smiles in seen_smiles:
                    continue
                seen_smiles.add(molecule.smiles)
                candidates.append(molecule)
                if len(candidates) >= desired_count:
                    return candidates

        return candidates

    @staticmethod
    def _apply_profile_fragment_addition(mol: Chem.Mol, profile: TargetGenerationProfile) -> Optional[str]:
        """Attach a target-preferred fragment when a chemically valid join is possible."""
        fragments = list(profile.preferred_fragments or ())
        random.shuffle(fragments)
        for fragment_smiles in fragments:
            fragment = Chem.MolFromSmiles(fragment_smiles)
            if fragment is None:
                continue
            atom_candidates = [
                atom.GetIdx()
                for atom in mol.GetAtoms()
                if atom.GetAtomicNum() in (6, 7, 8) and atom.GetTotalNumHs() > 0 and not atom.IsInRing()
            ]
            fragment_candidates = [
                atom.GetIdx()
                for atom in fragment.GetAtoms()
                if atom.GetAtomicNum() in (6, 7, 8) and atom.GetTotalNumHs() > 0
            ]
            if not atom_candidates or not fragment_candidates:
                continue
            random.shuffle(atom_candidates)
            random.shuffle(fragment_candidates)
            for attach_idx in atom_candidates[:3]:
                for fragment_idx in fragment_candidates[:3]:
                    try:
                        combined = Chem.CombineMols(mol, fragment)
                        edit_mol = Chem.EditableMol(combined)
                        edit_mol.AddBond(
                            attach_idx,
                            mol.GetNumAtoms() + fragment_idx,
                            Chem.BondType.SINGLE,
                        )
                        candidate = edit_mol.GetMol()
                        Chem.SanitizeMol(candidate)
                        return Chem.MolToSmiles(candidate)
                    except Exception as exc:
                        logger.debug("Profile fragment addition failed: %s", exc)
                        continue
        return None

    @staticmethod
    def generate_target_aware_variants(
        seed_smiles: str,
        n_molecules: int,
        profile: Optional[TargetGenerationProfile],
    ) -> List[str]:
        """Generate candidates from target scaffolds first, then seed analogs."""
        if profile is None:
            return MoleculeGenerationService.generate_variants(seed_smiles, n_molecules)

        seed_mol = Chem.MolFromSmiles(seed_smiles)
        if seed_mol is None:
            raise ValueError(f"Invalid seed SMILES: {seed_smiles}")
        try:
            Chem.SanitizeMol(seed_mol)
        except Exception as exc:
            raise ValueError(f"Invalid seed SMILES: {seed_smiles}") from exc

        candidates: List[str] = []
        seen = set()

        def add_candidate(smiles: str) -> None:
            mol, canonical = MoleculeGenerationService._sanitize_smiles(smiles)
            if mol is None or canonical is None or canonical in seen:
                return
            passes_filter, _metadata = MoleculeGenerationService._passes_target_prefilter(mol, profile)
            if not passes_filter:
                return
            seen.add(canonical)
            candidates.append(canonical)

        for scaffold in profile.scaffold_smiles:
            add_candidate(scaffold)
            if len(candidates) >= n_molecules:
                return candidates[:n_molecules]

        seed_passes_profile, _metadata = MoleculeGenerationService._passes_target_prefilter(seed_mol, profile)
        if seed_passes_profile:
            add_candidate(seed_smiles)

        seed_pool = [seed_smiles, *profile.scaffold_smiles]
        attempts_per_seed = max(4, n_molecules // max(1, len(seed_pool)) + 3)
        with MoleculeGenerationService._suppress_rdkit_warnings():
            for seed in seed_pool:
                if len(candidates) >= n_molecules:
                    break
                try:
                    for variant in MoleculeGenerationService.generate_variants(seed, attempts_per_seed):
                        add_candidate(variant)
                        if len(candidates) >= n_molecules:
                            break
                except Exception as exc:
                    logger.debug("Target-aware terminal analog generation failed: %s", exc)

                mol, _canonical = MoleculeGenerationService._sanitize_smiles(seed)
                if mol is None:
                    continue
                for _ in range(attempts_per_seed):
                    variant = MoleculeGenerationService._apply_profile_fragment_addition(mol, profile)
                    if variant:
                        add_candidate(variant)
                    if len(candidates) >= n_molecules:
                        break

        logger.info(
            "Generated %s target-aware %s candidates for %s",
            len(candidates),
            profile.inhibitor_type,
            profile.key,
        )
        return candidates[:n_molecules]

    @staticmethod
    def generate_variants(seed_smiles: str, n_molecules: int) -> List[str]:
        """
        Generate N molecular variants from seed SMILES via random mutations.
        
        Strategies:
        1. Random atom substitution (C→N, O→S, etc.)
        2. Fragment addition (add benzene, amide, etc.)
        
        Args:
            seed_smiles: Input SMILES string
            n_molecules: Number of variants to generate
            
        Returns:
            List of unique SMILES strings (valid molecules only)
        """
        seed_mol = Chem.MolFromSmiles(seed_smiles)
        if seed_mol is None:
            raise ValueError(f"Invalid seed SMILES: {seed_smiles}")
        try:
            Chem.SanitizeMol(seed_mol)
        except Exception as exc:
            raise ValueError(f"Invalid seed SMILES: {seed_smiles}") from exc

        variants = set()
        attempts = 0
        max_attempts = max(n_molecules * 12, 60)

        with MoleculeGenerationService._suppress_rdkit_warnings():
            while len(variants) < n_molecules and attempts < max_attempts:
                attempts += 1

                try:
                    mutation_strategy = random.choice(
                        (
                            MoleculeGenerationService._apply_terminal_substitution,
                            MoleculeGenerationService._apply_atom_substitution,
                            MoleculeGenerationService._apply_fragment_addition,
                        )
                    )
                    variant_smiles = mutation_strategy(seed_mol)

                    if not variant_smiles or variant_smiles == seed_smiles:
                        continue

                    sanitized_mol, sanitized_smiles = MoleculeGenerationService._sanitize_smiles(variant_smiles)
                    if sanitized_mol is None or sanitized_smiles is None or sanitized_smiles == seed_smiles:
                        continue

                    lipinski_data = MoleculeGenerationService.calculate_lipinski_descriptors(sanitized_mol)
                    if lipinski_data["lipinski_violations"] > 2:
                        continue

                    variants.add(sanitized_smiles)

                except Exception as e:
                    logger.debug(f"Generation attempt {attempts} failed: {e}")
                    continue
        
        logger.info(f"Generated {len(variants)} unique variants from {max_attempts} attempts")
        return list(variants)[:n_molecules]
    
    @staticmethod
    def _apply_atom_substitution(mol: Chem.Mol) -> Optional[str]:
        """
        Apply random atom substitution to molecule.
        Replace a random atom with another atom type.
        
        Example: C → N, O → S, etc.
        """
        mol_copy = Chem.RWMol(mol)
        n_atoms = mol_copy.GetNumAtoms()
        
        if n_atoms == 0:
            return None
        
        # Pick random atom
        atom_idx = random.randint(0, n_atoms - 1)
        atom = mol_copy.GetAtomWithIdx(atom_idx)
        
        # Get possible substitutions
        current_symbol = atom.GetSymbol()
        if current_symbol not in ATOM_SUBSTITUTIONS:
            # Try general substitution
            possible_symbols = ['N', 'O', 'S', 'C']
        else:
            possible_symbols = ATOM_SUBSTITUTIONS[current_symbol]
        
        # Pick random substitution
        new_symbol = random.choice(possible_symbols)
        
        # Avoid self-substitution
        if new_symbol == current_symbol:
            return None
        
        try:
            # Perform substitution
            atom.SetAtomicNum(Chem.GetPeriodicTable().GetAtomicNumber(new_symbol))
            
            # Convert to mol and validate
            variant_mol = mol_copy.GetMol()
            
            # Try to embed 3D (validates structure)
            if AllChem.EmbedMolecule(variant_mol, randomSeed=42) >= 0:
                variant_smiles = Chem.MolToSmiles(variant_mol)
                return variant_smiles if variant_smiles else None
        except Exception as e:
            logger.debug(f"Atom substitution failed: {e}")
            return None
        
        return None
    
    @staticmethod
    def _apply_fragment_addition(mol: Chem.Mol) -> Optional[str]:
        """
        Add a random fragment to the molecule.
        
        Example: Add benzene ring, amide group, etc.
        """
        try:
            # Pick random fragment
            fragment_smiles = random.choice(FRAGMENT_LIBRARY)
            fragment = Chem.MolFromSmiles(fragment_smiles)
            
            if fragment is None:
                return None
            
            # Pick random attachment point on original molecule
            n_atoms = mol.GetNumAtoms()
            if n_atoms == 0:
                return None
            
            attach_idx = random.randint(0, n_atoms - 1)
            
            # Combine molecules
            combined = Chem.CombineMols(mol, fragment)
            
            # Add bond between attach_idx and fragment start atom
            edit_mol = Chem.EditableMol(combined)
            fragment_start = mol.GetNumAtoms()
            
            if fragment_start < combined.GetNumAtoms():
                edit_mol.AddBond(attach_idx, fragment_start, Chem.BondType.SINGLE)
                combined = edit_mol.GetMol()
                
                # Try to embed 3D (validates structure)
                if AllChem.EmbedMolecule(combined, randomSeed=42) >= 0:
                    variant_smiles = Chem.MolToSmiles(combined)
                    return variant_smiles if variant_smiles else None
                    
        except Exception as e:
            logger.debug(f"Fragment addition failed: {e}")
            return None
        
        return None

    @staticmethod
    def _apply_terminal_substitution(mol: Chem.Mol) -> Optional[str]:
        """Perform conservative substitutions on terminal single-bond atoms only."""
        candidates: List[tuple[int, List[int]]] = []
        for atom in mol.GetAtoms():
            if atom.GetDegree() != 1 or atom.IsInRing():
                continue
            bonds = atom.GetBonds()
            if not bonds:
                continue
            bond = bonds[0]
            if bond.GetBondType() != Chem.BondType.SINGLE:
                continue
            neighbor = atom.GetNeighbors()[0]
            if neighbor.IsInRing():
                continue

            replacements = TERMINAL_ATOM_SUBSTITUTIONS.get(atom.GetAtomicNum(), [])
            if replacements:
                candidates.append((atom.GetIdx(), replacements))

        if not candidates:
            return None

        atom_idx, replacements = random.choice(candidates)
        replacement_atomic_num = random.choice(replacements)
        rw_mol = Chem.RWMol(Chem.Mol(mol))
        atom = rw_mol.GetAtomWithIdx(atom_idx)
        atom.SetAtomicNum(replacement_atomic_num)
        atom.SetFormalCharge(0)
        atom.SetNumExplicitHs(0)
        atom.SetNoImplicit(False)

        variant_mol = rw_mol.GetMol()
        Chem.SanitizeMol(variant_mol)
        return Chem.MolToSmiles(variant_mol)
    
    @staticmethod
    def calculate_lipinski_descriptors(
        mol: Chem.Mol,
        computed_properties: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Calculate Lipinski Rule of Five descriptors.
        
        Returns:
            {
                'molecular_weight': float,
                'hbd': int (H-bond donors),
                'hba': int (H-bond acceptors),
                'logp': float (lipophilicity),
                'lipinski_pass': bool
            }
        """
        try:
            properties = computed_properties or MoleculeGenerationService.compute_properties_from_smiles(Chem.MolToSmiles(mol))
            if not properties.get("smiles_valid"):
                raise ValueError("Invalid SMILES supplied for Lipinski calculation")

            mw = float(properties["mw"])
            hbd = int(properties["hbd"])
            hba = int(properties["hba"])
            logp = float(properties["logp"])
            
            violations = sum([
                mw > 500,
                logp > 5,
                hbd > 5,
                hba > 10,
            ])
            lipinski_pass = violations <= 2

            return {
                'molecular_weight': round(mw, 2),
                'hbd': int(hbd),
                'hba': int(hba),
                'logp': round(logp, 2),
                'lipinski_pass': lipinski_pass,
                'strict_lipinski_pass': violations == 0,
                'lipinski_violations': int(violations),
            }
        except Exception as e:
            logger.error(f"Error calculating Lipinski descriptors: {e}")
            return {
                'molecular_weight': 0.0,
                'hbd': 0,
                'hba': 0,
                'logp': 0.0,
                'lipinski_pass': False,
                'strict_lipinski_pass': False,
                'lipinski_violations': 4,
            }
    
    @staticmethod
    def calculate_sas_score(mol: Chem.Mol) -> float:
        """
        Calculate Synthetic Accessibility Score (SAS).
        
        Range: 1.0 (easy) to 10.0 (hard)
        
        Returns:
            SAS score (float between 1.0 and 10.0)
        """
        try:
            if SASCORER_AVAILABLE:
                score = sascorer.calculateScore(mol)
            else:
                # Heuristic fallback: larger, more aromatic, and more chiral molecules
                # are generally harder to synthesize.
                mw = rdMolDescriptors.CalcExactMolWt(mol)
                aromatic_rings = Descriptors.NumAromaticRings(mol)
                rotatable = Descriptors.NumRotatableBonds(mol)
                hetero_atoms = sum(
                    1 for atom in mol.GetAtoms() if atom.GetAtomicNum() not in (1, 6)
                )
                score = (
                    1.5
                    + min(3.0, mw / 250.0)
                    + min(2.0, aromatic_rings * 0.6)
                    + min(1.5, rotatable * 0.15)
                    + min(2.0, hetero_atoms * 0.12)
                )
            # Clamp to valid range
            return round(max(1.0, min(10.0, score)), 2)
        except Exception as e:
            logger.error(f"Error calculating SAS score: {e}")
            return 5.0  # Default middle score
    
    @staticmethod
    async def generate_molecules_for_target(
        target_id: str,
        seed_smiles: str,
        n_molecules: int,
        db: Session
    ) -> Tuple[List[Molecule], int]:
        """
        Generate and score molecules for a target.
        
        Pipeline:
        1. Generate N variants from seed SMILES
        2. For each variant:
           - Validate SMILES
           - Calculate Lipinski descriptors
           - Calculate SAS score
        3. Save to database
        4. Return created molecules and count
        
        Args:
            target_id: UUID of target
            seed_smiles: Seed SMILES string
            n_molecules: Number of molecules to generate
            db: SQLAlchemy session
            
        Returns:
            Tuple of (list of Molecule objects, count of valid molecules)
        """
        # Validate target exists
        target = db.query(Target).filter(Target.id == target_id).first()
        if not target:
            raise ValueError(f"Target {target_id} not found")
        
        target_profile = MoleculeGenerationService._profile_for_target(target)

        # Generate variants
        try:
            variant_smiles_list = MoleculeGenerationService.generate_target_aware_variants(
                seed_smiles,
                n_molecules,
                target_profile,
            )
        except Exception as e:
            logger.error(f"Variant generation failed: {e}")
            raise ValueError(f"Failed to generate variants: {e}")
        
        # Score and validate each molecule
        molecules = []
        
        for smiles in variant_smiles_list:
            try:
                molecule = MoleculeGenerationService._build_molecule_record(
                    target_id=target_id,
                    smiles=smiles,
                    source="target_aware_generated" if target_profile else "rdkit_generated",
                    target_profile=target_profile,
                    require_target_prefilter=target_profile is not None,
                )
                if molecule is not None:
                    molecules.append(molecule)
            except Exception as e:
                logger.warning(f"Error processing SMILES {smiles}: {e}")
                continue

        saved_molecules, valid_count = MoleculeGenerationService._persist_unique_molecules(target_id, db, molecules)
        if target_profile and not saved_molecules:
            raise ValueError(
                f"No generated molecules matched the {target_profile.key} pharmacophore, early ADMET, and quick-binding filters"
            )
        return saved_molecules, valid_count

    @staticmethod
    async def generate_molecules(
        target_context: TargetContext,
        db: Session,
        seed_smiles: str | None = None,
        n_molecules: int = 20,
    ) -> Tuple[List[Molecule], int]:
        """Generate or fetch molecules using a single immutable target context."""
        dynamic_profile = build_target_profile(target_context)
        target_profile = MoleculeGenerationService._profile_for_target_context(target_context)

        if seed_smiles:
            try:
                variant_smiles_list = MoleculeGenerationService.generate_target_aware_variants(
                    seed_smiles,
                    n_molecules,
                    target_profile,
                )
            except Exception as exc:
                logger.error("Variant generation failed for %s: %s", target_context.target_id, exc)
                raise ValueError(f"Failed to generate variants: {exc}") from exc

            molecules: List[Molecule] = []
            for smiles in variant_smiles_list:
                try:
                    molecule = MoleculeGenerationService._build_molecule_record(
                        target_id=target_context.target_id,
                        smiles=smiles,
                        source="target_aware_generated" if target_profile else "rdkit_generated",
                        target_profile=target_profile,
                        require_target_prefilter=target_profile is not None,
                    )
                    if molecule is not None:
                        molecules.append(molecule)
                except Exception as exc:
                    logger.warning("Error processing SMILES %s for %s: %s", smiles, target_context.target_id, exc)

            saved_molecules, valid_count = MoleculeGenerationService._persist_unique_molecules(
                target_context.target_id,
                db,
                molecules,
            )
            if target_profile and not saved_molecules:
                raise ValueError(
                    f"No generated molecules matched the {target_profile.key} pharmacophore, early ADMET, and quick-binding filters"
                )
            return saved_molecules, valid_count

        molecules, valid_count = await MoleculeGenerationService.fetch_known_molecules_for_target(
            target_id=target_context.target_id,
            target_name=target_context.protein_name,
            target_chembl_id=target_context.chembl_id or None,
            n_molecules=n_molecules,
            db=db,
            target_context=target_context,
        )
        if not molecules:
            raise ValueError(
                f"No molecules generated for target class {dynamic_profile['target_class']} using canonical ChEMBL target {target_context.chembl_id or 'N/A'}"
            )
        return molecules, valid_count

    @staticmethod
    async def fetch_known_molecules_for_target(
        target_id: str,
        target_name: str,
        target_chembl_id: Optional[str],
        n_molecules: int,
        db: Session,
        target_context: TargetContext | None = None,
    ) -> Tuple[List[Molecule], int]:
        """Fetch known bioactive molecules for a target from ChEMBL instead of generating variants."""
        if target_context is not None:
            profile_dict = build_target_profile(target_context)
            target_profile = MoleculeGenerationService._profile_for_target_context(target_context)
            target_class = profile_dict["target_class"]
            target_chembl_id = target_context.chembl_id or None
        else:
            target = db.query(Target).filter(Target.id == target_id).first()
            if not target:
                raise ValueError(f"Target {target_id} not found")
            target_profile = MoleculeGenerationService._profile_for_target(target)
            target_class = "generic"

        compounds: List[Dict[str, str]] = []
        fetch_limit = max(200, n_molecules * 6)
        if target_chembl_id:
            try:
                compounds = await MoleculeGenerationService._fetch_chembl_activity_molecules(
                    target_chembl_id,
                    MoleculeGenerationService._infer_gene_symbol(target_name),
                    fetch_limit,
                    allow_target_fallback_ids=target_context is None,
                )
            except Exception as exc:
                logger.error("Failed to fetch ChEMBL compounds for %s: %s", target_chembl_id, exc)
                raise ValueError("Failed to fetch related molecules from ChEMBL") from exc
        else:
            logger.warning("No ChEMBL target was found for %s - using emergency fallback seeds if needed", target_name)

        run_candidates: List[Molecule] = []
        existing_count = 0

        seeds, all_seeds_exceeded_mw = MoleculeGenerationService._collect_analog_generation_seeds(compounds[:10])
        if seeds:
            needed = max(n_molecules * 2, n_molecules * 3, 12)
            expanded_compounds = MoleculeGenerationService._expand_seed_compounds(seeds, desired_count=needed)
            if expanded_compounds:
                logger.info(
                    "Expanded %s fetched ChEMBL compounds into %s analog candidates for target %s",
                    len(seeds),
                    len(expanded_compounds),
                    target_id,
                )
                for compound in expanded_compounds:
                    molecule = MoleculeGenerationService._build_molecule_record(
                        target_id=target_id,
                        smiles=compound["smiles"],
                        source=compound.get("source") or "chembl_seed_expanded",
                        source_id=compound.get("chembl_id"),
                        target_profile=target_profile,
                        require_target_prefilter=target_profile is not None,
                    )
                    if molecule is not None:
                        run_candidates.append(molecule)

        if all_seeds_exceeded_mw:
            logger.info("All seeds exceeded MW threshold - falling back to direct ChEMBL actives save")

        saved_molecules, valid_count, existing_from_primary = MoleculeGenerationService._persist_candidates(
            target_id,
            db,
            MoleculeGenerationService._sort_candidates(run_candidates)[:n_molecules],
            require_lipinski_pass=False,
        )
        existing_count += existing_from_primary

        if not saved_molecules:
            direct_candidates = MoleculeGenerationService._build_direct_chembl_candidates(
                target_id,
                compounds,
                max_lipinski_violations=2,
                source_label="chembl_direct_fallback",
            )
            logger.info(
                "Direct actives save: %s molecules passed relaxed Lipinski (up to 2 violations)",
                len(direct_candidates),
            )
            saved_molecules, valid_count, existing_from_direct = MoleculeGenerationService._persist_candidates(
                target_id,
                db,
                MoleculeGenerationService._sort_candidates(direct_candidates)[:n_molecules],
                require_lipinski_pass=False,
            )
            existing_count += existing_from_direct

        if not saved_molecules:
            relaxed_candidates = MoleculeGenerationService._build_emergency_fallback_candidates(
                target_id,
                target_class,
                target_profile,
                max(n_molecules, 10),
            )
            logger.info(
                "Emergency fallback generation produced %s relaxed small-molecule candidates",
                len(relaxed_candidates),
            )
            saved_molecules, valid_count, existing_from_relaxed = MoleculeGenerationService._persist_candidates(
                target_id,
                db,
                MoleculeGenerationService._sort_candidates(relaxed_candidates)[: max(n_molecules, 10)],
                require_lipinski_pass=False,
            )
            existing_count += existing_from_relaxed

        if not saved_molecules:
            logger.warning("No viable molecules found after all fallbacks for target %s", target_id)
            raise ValueError("No molecules generated")

        logger.info(
            "Pipeline run saved %s molecules for target %s (%s new, %s already existed)",
            len(saved_molecules) + existing_count,
            target_id,
            len(saved_molecules),
            existing_count,
        )

        ranked_molecules = MoleculeGenerationService._sort_candidates(saved_molecules)
        return ranked_molecules[:n_molecules], valid_count
    
    @staticmethod
    def get_molecules_for_target(
        target_id: str,
        db: Session,
        skip: int = 0,
        limit: int = 100
    ) -> List[Molecule]:
        """
        Retrieve all molecules for a target with pagination.
        
        Args:
            target_id: UUID of target
            db: SQLAlchemy session
            skip: Number of records to skip
            limit: Max records to return
            
        Returns:
            List of Molecule objects
        """
        molecules = db.query(Molecule).filter(
            Molecule.target_id == target_id
        ).offset(skip).limit(limit).all()
        
        return molecules

    @staticmethod
    def get_molecules_by_ids(molecule_ids: List[str], db: Session) -> List[Molecule]:
        """Retrieve only the requested molecule IDs, preserving request order and skipping missing rows."""
        if not molecule_ids:
            return []

        requested_ids = [str(molecule_id) for molecule_id in molecule_ids]
        molecules = db.query(Molecule).filter(Molecule.id.in_(requested_ids)).all()
        by_id = {str(molecule.id): molecule for molecule in molecules}
        return [by_id[molecule_id] for molecule_id in requested_ids if molecule_id in by_id]
    
    @staticmethod
    def get_molecules_count(target_id: str, db: Session) -> int:
        """Get total molecule count for a target."""
        count = db.query(Molecule).filter(
            Molecule.target_id == target_id
        ).count()
        return count
