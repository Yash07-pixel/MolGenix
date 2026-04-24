"""
Reports Router - PDF report generation and download endpoints.
"""

import logging
from pathlib import Path
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.report import Report
from app.services.report_service import ReportService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports", tags=["reports"])


class GenerateReportRequest(BaseModel):
    """Request schema for generating a report."""

    target_id: UUID = Field(..., description="UUID of the target")
    molecule_ids: List[UUID] = Field(default_factory=list, description="Optional molecule IDs to scope the report to a specific run")


class GenerateReportResponse(BaseModel):
    """Response schema for report generation."""

    report_id: UUID
    pdf_url: str


@router.post("/generate", response_model=GenerateReportResponse, status_code=status.HTTP_200_OK)
async def generate_report(
    request: GenerateReportRequest,
    db: Session = Depends(get_db),
) -> GenerateReportResponse:
    """Generate and persist a PDF report for a target."""
    try:
        result = await ReportService.generate_report(
            str(request.target_id),
            db,
            molecule_ids=[str(molecule_id) for molecule_id in request.molecule_ids] or None,
        )
        return GenerateReportResponse(report_id=result["report_id"], pdf_url=result["pdf_url"])
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Report generation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Report generation failed",
        ) from exc


@router.get("/{report_id}/download", status_code=status.HTTP_200_OK)
async def download_report(
    report_id: UUID,
    db: Session = Depends(get_db),
):
    """Stream a persisted report PDF by report ID."""
    try:
        report = db.query(Report).filter(Report.id == report_id).first()
        if not report:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

        pdf_path = report.pdf_path
        if not pdf_path:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report file not found")

        file_path = Path(pdf_path)
        if not file_path.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report file not found")

        return FileResponse(
            path=file_path,
            media_type="application/pdf",
            filename=file_path.name,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Report download failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Report download failed",
        ) from exc
