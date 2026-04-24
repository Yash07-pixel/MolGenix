"""
Docking Router - FastAPI endpoints for molecular docking.
"""

import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.docking_service import DockingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/docking", tags=["docking"])


class RunDockingRequest(BaseModel):
    """Request schema for running docking."""

    molecule_id: UUID = Field(..., description="UUID of the molecule to dock")
    pdb_filename: str = Field(..., min_length=1, description="Receptor PDB filename in data/pdb_files")


class RunDockingResponse(BaseModel):
    """Response schema for a docking run."""

    molecule_id: UUID
    docking_score: float
    method: str
    is_mock: bool
    fallback_reason: str | None = None
    pdb_filename: str


class DockingResultItem(BaseModel):
    """Single stored docking result."""

    molecule_id: UUID
    target_id: UUID
    smiles: str
    docking_score: float


class DockingResultsResponse(BaseModel):
    """Response schema for docking result listing."""

    count: int
    target_id: UUID
    results: List[DockingResultItem]


@router.post("/run", response_model=RunDockingResponse, status_code=status.HTTP_200_OK)
async def run_docking(
    request: RunDockingRequest,
    db: Session = Depends(get_db),
) -> RunDockingResponse:
    """Run docking for a molecule against a receptor PDB."""
    try:
        result = await DockingService.run_docking(
            molecule_id=str(request.molecule_id),
            pdb_filename=request.pdb_filename,
            db=db,
        )
        return RunDockingResponse(**result)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Docking run failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Docking run failed",
        ) from exc


@router.get("/results/{target_id}", response_model=DockingResultsResponse, status_code=status.HTTP_200_OK)
async def get_docking_results(
    target_id: UUID,
    db: Session = Depends(get_db),
) -> DockingResultsResponse:
    """Get all docked molecules for a target sorted by best score first."""
    try:
        results = DockingService.get_docking_results_for_target(str(target_id), db)
        return DockingResultsResponse(
            count=len(results),
            target_id=target_id,
            results=[DockingResultItem(**result) for result in results],
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Failed to fetch docking results: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch docking results",
        ) from exc
