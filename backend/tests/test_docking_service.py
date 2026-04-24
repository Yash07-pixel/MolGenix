import importlib
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def test_rdkit_fallback_result_when_binaries_missing(monkeypatch):
    import app.services.docking_service as docking_service

    monkeypatch.setattr(docking_service.shutil, "which", lambda _name: None)
    reloaded = importlib.reload(docking_service)
    try:
        result = reloaded.DockingService._fallback_result(
            "CC(=O)Oc1ccccc1C(=O)O",
            "vina_not_found",
        )
        assert -12.0 <= result["docking_score"] <= -2.0
        assert result["method"] == "rdkit_fallback"
        assert result["is_mock"] is True
        assert result["fallback_reason"] == "vina_not_found"
    finally:
        importlib.reload(reloaded)
