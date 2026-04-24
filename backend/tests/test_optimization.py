"""
Unit tests for lead optimization.
"""

import pytest

pytest.importorskip("rdkit.Chem", reason="RDKit is required for optimization tests")

from app.services.optimization_service import OptimizationService


def test_optimize_aspirin_returns_different_smiles_and_passes_lipinski():
    """Optimizing aspirin should yield a different, Lipinski-compliant variant."""
    aspirin = "CC(=O)Oc1ccccc1C(=O)O"

    result = OptimizationService.optimize_smiles(aspirin)

    assert result["optimized"]["smiles"] != aspirin
    assert result["optimized"]["lipinski_pass"] is True
    assert result["changes"]
