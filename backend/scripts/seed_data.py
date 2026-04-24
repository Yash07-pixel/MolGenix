"""
Seed MolGenix with ChEMBL molecules, receptor PDB files, and baseline targets.
"""

from __future__ import annotations

import asyncio
import csv
import logging
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import requests
from rdkit import Chem

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.database import SessionLocal, init_db  # noqa: E402
from app.models.molecule import Molecule  # noqa: E402
from app.models.target import Target  # noqa: E402
from app.services.molecule_service import MoleculeGenerationService  # noqa: E402
from app.services.target_service import TargetEnrichmentService  # noqa: E402

logger = logging.getLogger("seed_data")

CHEMBL_URL = (
    "https://www.ebi.ac.uk/chembl/api/data/molecule"
    "?format=json&limit=500&molecular_weight__lte=500&alogp__lte=5&hbd__lte=5&hba__lte=10"
)
PDB_URL_TEMPLATE = "https://files.rcsb.org/download/{pdb_id}.pdb"

CHEMBL_SEED_DIR = ROOT_DIR / "data" / "chembl_seed"
PDB_DIR = ROOT_DIR / "data" / "pdb_files"
CHEMBL_CSV_PATH = CHEMBL_SEED_DIR / "chembl_500.csv"

TARGET_CONFIGS = [
    {
        "key": "bace1",
        "query": "BACE1 beta-secretase in Alzheimer's disease",
        "pdb_id": "2QMG",
        "disease": "Alzheimer's",
        "seed_terms": ["verubecestat", "lanabecestat", "bace"],
        "manual_seed": {
            "chembl_id": "MANUAL-BACE1",
            "smiles": "CN1CCN(CC1)C2=NC3=CC=CC=C3N2CC4=CC=C(C=C4)F",
            "name": "Verubecestat-like",
            "molecular_weight": 410.49,
        },
    },
    {
        "key": "egfr",
        "query": "EGFR epidermal growth factor receptor in lung cancer",
        "pdb_id": "1IEP",
        "disease": "Lung cancer",
        "seed_terms": ["gefitinib", "erlotinib", "afatinib", "osimertinib"],
        "manual_seed": {
            "chembl_id": "MANUAL-EGFR",
            "smiles": "COC1=C(C=C2C(=C1)N=CN=C2NC3=CC=CC=C3Cl)OCCCN4CCOCC4",
            "name": "Gefitinib-like",
            "molecular_weight": 446.90,
        },
    },
    {
        "key": "hiv_protease",
        "query": "HIV-1 protease in HIV AIDS",
        "pdb_id": "1HVR",
        "disease": "HIV/AIDS",
        "seed_terms": ["ritonavir", "lopinavir", "indinavir", "saquinavir"],
        "manual_seed": {
            "chembl_id": "MANUAL-HIVP",
            "smiles": "CC(C)NC(=O)C(CC1=CC=CC=C1)NC(=O)C(C(C)C)NC(=O)OC(C)(C)C",
            "name": "Ritonavir-like",
            "molecular_weight": 573.77,
        },
    },
    {
        "key": "cox2",
        "query": "COX-2 cyclooxygenase in inflammation and pain",
        "pdb_id": "1CX2",
        "disease": "Inflammation",
        "seed_terms": ["celecoxib", "rofecoxib", "valdecoxib", "etoricoxib"],
        "manual_seed": {
            "chembl_id": "MANUAL-COX2",
            "smiles": "CC1=CC=C(C=C1)C2=NN(C(=C2)S(=O)(=O)N)C3=CC=CC=C3",
            "name": "Celecoxib-like",
            "molecular_weight": 381.37,
        },
    },
]


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def ensure_directories() -> None:
    CHEMBL_SEED_DIR.mkdir(parents=True, exist_ok=True)
    PDB_DIR.mkdir(parents=True, exist_ok=True)


def _safe_smiles(molecule_record: Dict[str, object]) -> Optional[str]:
    structures = molecule_record.get("molecule_structures") or {}
    if not isinstance(structures, dict):
        return None
    smiles = structures.get("canonical_smiles")
    return smiles if isinstance(smiles, str) and smiles.strip() else None


def fetch_chembl_seed_rows() -> List[Dict[str, object]]:
    logger.info("Fetching ChEMBL seed compounds from %s", CHEMBL_URL)
    response = requests.get(CHEMBL_URL, timeout=60)
    response.raise_for_status()
    payload = response.json()

    fetched = payload.get("molecules", [])
    valid_rows: List[Dict[str, object]] = []

    for item in fetched:
        if not isinstance(item, dict):
            continue

        smiles = _safe_smiles(item)
        if not smiles:
            continue

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            continue

        properties = item.get("molecule_properties") or {}
        if not isinstance(properties, dict):
            properties = {}

        valid_rows.append(
            {
                "chembl_id": item.get("molecule_chembl_id", ""),
                "smiles": smiles,
                "name": item.get("pref_name") or "",
                "molecular_weight": properties.get("full_mwt") or "",
            }
        )

    with CHEMBL_CSV_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["chembl_id", "smiles", "name", "molecular_weight"],
        )
        writer.writeheader()
        writer.writerows(valid_rows)

    logger.info(
        "ChEMBL seed complete: fetched=%s valid=%s saved=%s path=%s",
        len(fetched),
        len(valid_rows),
        len(valid_rows),
        CHEMBL_CSV_PATH,
    )
    return valid_rows


def download_pdb_files() -> None:
    for config in TARGET_CONFIGS:
        pdb_id = config["pdb_id"]
        destination = PDB_DIR / f"{pdb_id.lower()}.pdb"
        url = PDB_URL_TEMPLATE.format(pdb_id=pdb_id)
        logger.info("Downloading %s from %s", pdb_id, url)

        response = requests.get(url, timeout=60)
        response.raise_for_status()
        destination.write_bytes(response.content)

        size = destination.stat().st_size if destination.exists() else 0
        if size <= 10 * 1024:
            raise RuntimeError(f"Downloaded PDB file is too small: {destination} ({size} bytes)")

        logger.info("Saved %s (%s bytes) to %s", pdb_id, size, destination)


def _find_seed_row(rows: Iterable[Dict[str, object]], terms: List[str]) -> Optional[Dict[str, object]]:
    for row in rows:
        name = str(row.get("name") or "").lower()
        chembl_id = str(row.get("chembl_id") or "").lower()
        if any(term in name or term in chembl_id for term in terms):
            return row
    return None


async def seed_database(rows: List[Dict[str, object]]) -> None:
    db = SessionLocal()
    targets_before = db.query(Target).count()
    molecules_before = db.query(Molecule).count()
    inserted_targets = 0
    inserted_molecules = 0

    try:
        for config in TARGET_CONFIGS:
            target_count_before = db.query(Target).count()
            target = await TargetEnrichmentService.analyze_target(config["query"], db)
            target_count_after = db.query(Target).count()
            if target_count_after > target_count_before:
                inserted_targets += 1

            seed_row = _find_seed_row(rows, config["seed_terms"]) or config["manual_seed"]
            logger.info(
                "Using seed for %s: %s (%s)",
                config["key"],
                seed_row.get("name") or seed_row.get("chembl_id"),
                seed_row["smiles"],
            )

            molecules, _valid_count = await MoleculeGenerationService.generate_molecules_for_target(
                target_id=str(target.id),
                seed_smiles=str(seed_row["smiles"]),
                n_molecules=10,
                db=db,
            )
            inserted_molecules += len(molecules)

        targets_after = db.query(Target).count()
        molecules_after = db.query(Molecule).count()
        logger.info(
            "DB seed complete: targets_inserted=%s molecules_inserted=%s total_targets=%s total_molecules=%s",
            inserted_targets,
            inserted_molecules,
            targets_after,
            molecules_after,
        )
        logger.info(
            "DB delta check: targets_before=%s targets_after=%s molecules_before=%s molecules_after=%s",
            targets_before,
            targets_after,
            molecules_before,
            molecules_after,
        )
    finally:
        db.close()


async def main() -> None:
    configure_logging()
    ensure_directories()
    init_db()
    chembl_rows = fetch_chembl_seed_rows()
    download_pdb_files()
    await seed_database(chembl_rows)


if __name__ == "__main__":
    asyncio.run(main())
