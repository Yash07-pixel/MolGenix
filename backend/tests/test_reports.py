"""
Basic report generation tests.
"""

from pathlib import Path

import pytest

pytest.importorskip("reportlab", reason="ReportLab is required for PDF report tests")


def test_report_service_module_imports():
    """Report service should import cleanly."""
    from app.services.report_service import ReportService

    assert ReportService is not None
