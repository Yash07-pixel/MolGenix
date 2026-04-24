from __future__ import annotations

import os
import sys
import time
import warnings
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List

import httpx
import pytest
from rdkit import Chem

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.database import SessionLocal
from app.models.molecule import Molecule
from app.models.report import Report

pytestmark = pytest.mark.integration

BASE_URL = os.getenv("MOLGENIX_BASE_URL", "http://backend:8000")
REQUEST_TIMEOUT = float(os.getenv("MOLGENIX_E2E_TIMEOUT", "180"))
STARTUP_WAIT_SECONDS = float(os.getenv("MOLGENIX_STARTUP_WAIT", "60"))

SUMMARY: "OrderedDict[str, Dict[str, str]]" = OrderedDict()


def _record_summary(module: str, status: str, metric: str) -> None:
    SUMMARY[module] = {"status": status, "metric": metric}


def _print_summary() -> None:
    print("\nModule              Status     Key Metric")
    print("-----------------------------------------------")
    for module, result in SUMMARY.items():
        print(f"{module:<19} {result['status']:<10} {result['metric']}")


@pytest.fixture(scope="session")
def client() -> httpx.Client:
    with httpx.Client(base_url=BASE_URL, timeout=REQUEST_TIMEOUT) as session:
        deadline = time.monotonic() + STARTUP_WAIT_SECONDS
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                response = session.get("/health")
                if response.status_code == 200:
                    break
            except httpx.HTTPError as exc:
                last_error = exc
            time.sleep(1)
        else:
            raise RuntimeError(f"Backend did not become healthy at {BASE_URL}") from last_error
        yield session


@pytest.fixture(scope="session", autouse=True)
def summary_printer() -> None:
    yield
    _print_summary()


@pytest.fixture(scope="session")
def state() -> Dict[str, Any]:
    return {}


def _get_db_value(model: Any, pk: str) -> Any:
    db = SessionLocal()
    try:
        return db.query(model).filter(model.id == pk).first()
    finally:
        db.close()


def test_1_health_check(client: httpx.Client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    _record_summary("Health Check", "PASS", "200 OK")


def test_2_target_analysis(client: httpx.Client, state: Dict[str, Any]) -> None:
    response = client.post(
        "/api/targets/analyze",
        json={"name": "BACE1 beta-secretase in Alzheimer's disease"},
    )
    assert response.status_code == 201
    payload = response.json()

    assert payload["id"]
    assert isinstance(payload["name"], str) and payload["name"].strip()
    assert payload.get("uniprot_id") is None or isinstance(payload["uniprot_id"], str)
    assert isinstance(payload["druggability_score"], float)
    assert 0.0 <= payload["druggability_score"] <= 1.0

    state["target_id"] = payload["id"]
    _record_summary(
        "Target Analysis",
        "PASS",
        f"druggability={payload['druggability_score']:.2f}",
    )


def test_3_molecule_generation(client: httpx.Client, state: Dict[str, Any]) -> None:
    response = client.post(
        "/api/molecules/generate",
        json={
            "target_id": state["target_id"],
            "seed_smiles": "CC(=O)Oc1ccccc1C(=O)O",
            "n_molecules": 10,
        },
    )
    assert response.status_code == 201
    payload = response.json()

    molecules = payload["molecules"]
    assert len(molecules) >= 5
    assert payload["count"] == len(molecules)
    assert payload["valid_count"] >= 1

    for molecule in molecules:
        assert molecule["id"]
        assert molecule["smiles"]
        assert isinstance(molecule["lipinski_pass"], bool)
        assert isinstance(molecule["sas_score"], float)
        assert Chem.MolFromSmiles(molecule["smiles"]) is not None

    assert any(molecule["lipinski_pass"] for molecule in molecules)

    state["molecule_ids"] = [molecule["id"] for molecule in molecules[:3]]
    _record_summary(
        "Molecule Gen",
        "PASS",
        f"{len(molecules)}/10 returned",
    )


def test_4_admet_prediction(client: httpx.Client, state: Dict[str, Any]) -> None:
    molecule_ids = state["molecule_ids"]
    response = client.post("/api/admet/predict", json={"molecule_ids": molecule_ids})
    assert response.status_code == 200
    payload = response.json()

    results = payload["results"]
    assert len(results) == 3

    for result in results:
        admet = result["admet"]
        assert admet["bbbp_score"] is None or 0.0 <= admet["bbbp_score"] <= 1.0
        assert admet["hepatotoxicity_score"] is None or 0.0 <= admet["hepatotoxicity_score"] <= 1.0
        assert 0.0 <= admet["bioavailability_score"] <= 1.0
        assert admet["solubility_score"] is None or 0.0 <= admet["solubility_score"] <= 1.0
        assert admet["clearance_score"] is None or 0.0 <= admet["clearance_score"] <= 1.0
        assert admet["cyp3a4_liability"] is None or 0.0 <= admet["cyp3a4_liability"] <= 1.0
        assert isinstance(admet["herg_risk"], bool)
        assert 0.0 <= admet["herg_confidence"] <= 1.0
        for key in [
            "bbbp_traffic",
            "hepatotoxicity_traffic",
            "bioavailability_traffic",
            "solubility_traffic",
            "clearance_traffic",
            "cyp3a4_traffic",
        ]:
            assert admet[key] in {"green", "yellow", "red", "unknown"}
        assert admet["model_source"] in {"deepchem_hybrid", "heuristic"}

        db_molecule = _get_db_value(Molecule, result["molecule_id"])
        assert db_molecule is not None
        assert isinstance(db_molecule.admet_scores, dict)
        assert "bbbp_score" in db_molecule.admet_scores

    _record_summary("ADMET", "PASS", f"{len(results)} molecules scored")


def test_5_docking(client: httpx.Client, state: Dict[str, Any]) -> None:
    molecule_id = state["molecule_ids"][0]
    response = client.post(
        "/api/docking/run",
        json={"molecule_id": molecule_id, "pdb_filename": "2qmg.pdb"},
    )
    assert response.status_code == 200
    payload = response.json()

    assert isinstance(payload["docking_score"], float)
    assert -15.0 <= payload["docking_score"] <= -1.0
    assert payload["method"] in {"vina", "rdkit_fallback"}
    assert isinstance(payload["is_mock"], bool)
    if payload["is_mock"]:
        assert payload["fallback_reason"] is not None

    db_molecule = _get_db_value(Molecule, molecule_id)
    assert db_molecule is not None
    assert db_molecule.docking_score is not None

    status = "PASS"
    if payload["is_mock"]:
        warnings.warn("Docking returned mock fallback result", stacklevel=1)
        status = "MOCK"

    _record_summary(
        "Docking",
        status,
        f"score={payload['docking_score']:.2f}",
    )


def test_6_lead_optimization(client: httpx.Client, state: Dict[str, Any]) -> None:
    molecule_id = state["molecule_ids"][0]
    response = client.post("/api/optimize/molecule", json={"molecule_id": molecule_id})
    assert response.status_code == 200
    payload = response.json()

    assert payload["original"]
    assert payload["optimized"]
    assert payload["changes"]
    assert payload["optimized"]["smiles"] != payload["original"]["smiles"]
    assert isinstance(payload["optimized"]["lipinski_pass"], bool)
    assert isinstance(payload["changes"], list) and len(payload["changes"]) > 0

    optimized_id = payload["optimized"]["molecule_id"]
    db_molecule = _get_db_value(Molecule, optimized_id)
    assert db_molecule is not None
    assert db_molecule.is_optimized is True

    state["optimized_molecule_id"] = optimized_id
    _record_summary("Optimization", "PASS", "SMILES changed")


def test_7_report_generation(client: httpx.Client, state: Dict[str, Any]) -> None:
    response = client.post("/api/reports/generate", json={"target_id": state["target_id"]})
    assert response.status_code == 200
    payload = response.json()

    assert payload["report_id"]
    assert payload["pdf_url"]

    pdf_response = client.get(payload["pdf_url"])
    assert pdf_response.status_code == 200
    assert "application/pdf" in pdf_response.headers.get("content-type", "")
    assert len(pdf_response.content) > 50 * 1024

    report = _get_db_value(Report, payload["report_id"])
    assert report is not None
    assert Path(report.pdf_path).exists()

    _record_summary("Report Gen", "PASS", f"PDF={len(pdf_response.content) // 1024}KB")


def test_8_full_pipeline(client: httpx.Client) -> None:
    start = time.monotonic()
    response = client.post(
        "/api/pipeline/run",
        json={
            "query": "EGFR kinase in non-small cell lung cancer",
            "seed_smiles": "c1ccc2ncccc2c1",
            "n_molecules": 10,
        },
        timeout=180,
    )
    elapsed = time.monotonic() - start

    assert response.status_code == 200
    assert elapsed <= 120

    payload = response.json()
    assert payload["target"]
    assert payload["molecules"]
    assert len(payload["molecules"]) >= 3
    assert payload["optimized_lead"] is not None
    assert payload["report_url"]

    report_response = client.get(payload["report_url"])
    assert report_response.status_code == 200

    _record_summary("Full Pipeline", "PASS", f"{elapsed:.1f}s")
