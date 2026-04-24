"""
Mocked integration test for the pipeline endpoint.
"""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("pydantic_settings")

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


def test_pipeline_run_returns_all_sections():
    target_id = uuid4()
    molecule_ids = [uuid4() for _ in range(3)]
    now = datetime.now(timezone.utc)

    target = SimpleNamespace(
        id=target_id,
        name="BACE1",
        uniprot_id="P56817",
        druggability_score=0.9,
        created_at=now,
    )
    molecules = [
        SimpleNamespace(
            id=molecule_ids[index],
            target_id=target_id,
            smiles=f"SMILES-{index}",
            lipinski_pass=True,
            sas_score=2.0 + index,
            admet_scores=None,
            docking_score=None,
            is_optimized=False,
            created_at=now,
        )
        for index in range(3)
    ]
    admet_results = [
        {
            "molecule_id": str(molecule.id),
            "smiles": molecule.smiles,
            "admet": {
                "bbbp_score": 0.8,
                "bbbp_traffic": "green",
                "hepatotoxicity_score": 0.2,
                "hepatotoxicity_traffic": "red",
                "herg_risk": False,
                "herg_confidence": 0.1,
                "bioavailability_score": 0.9,
                "bioavailability_traffic": "green",
            },
        }
        for molecule in molecules
    ]

    with patch("app.main.TargetEnrichmentService.analyze_target", new=AsyncMock(return_value=target)), \
         patch("app.main.MoleculeGenerationService.generate_molecules_for_target", new=AsyncMock(return_value=(molecules, 3))), \
         patch("app.main.ADMETService.predict_admet_for_molecules", new=AsyncMock(return_value=admet_results)), \
         patch("app.main.DockingService.run_docking", new=AsyncMock(side_effect=[
             {"molecule_id": str(molecule_ids[0]), "docking_score": -8.1, "method": "vina", "is_mock": False, "fallback_reason": None, "pdb_filename": "2qmg.pdb"},
             {"molecule_id": str(molecule_ids[1]), "docking_score": -7.9, "method": "vina", "is_mock": False, "fallback_reason": None, "pdb_filename": "2qmg.pdb"},
             {"molecule_id": str(molecule_ids[2]), "docking_score": -7.5, "method": "vina", "is_mock": False, "fallback_reason": None, "pdb_filename": "2qmg.pdb"},
         ])), \
         patch("app.main.OptimizationService.optimize_molecule", new=AsyncMock(return_value={
             "original": {"smiles": "SMILES-0", "sas_score": 2.0, "lipinski_pass": True, "admet_scores": admet_results[0]["admet"], "docking_score": -8.1},
             "optimized": {"smiles": "OPT-SMILES", "sas_score": 1.8, "lipinski_pass": True, "admet_scores": admet_results[0]["admet"], "combined_score": 0.88, "molecule_id": str(uuid4())},
             "changes": ["Added F on aromatic ring site 1"],
         })), \
         patch("app.main.ReportService.generate_report", new=AsyncMock(return_value={"report_id": str(uuid4()), "pdf_url": "/api/reports/download/test-report", "pdf_path": "data/reports/test.pdf"})), \
         patch("app.main._find_default_pdb_filename", return_value="2qmg.pdb"):
        client = TestClient(app)
        response = client.post(
            "/api/pipeline/run",
            json={
                "query": "BACE1 in Alzheimer's",
                "seed_smiles": "CC(=O)Oc1ccccc1C(=O)O",
                "n_molecules": 10,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    for key in ["target", "molecules", "admet_results", "docking_results", "optimized_lead", "report_url"]:
        assert key in payload
    assert payload["report_url"].startswith("/api/reports/download/")
    assert payload["molecules"]
    assert all("admet_scores" in molecule and molecule["admet_scores"] for molecule in payload["molecules"])
