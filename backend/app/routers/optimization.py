"""
Optimization Router - FastAPI endpoints for lead optimization.
"""

import logging
from typing import Any, Dict, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.optimization_service import OptimizationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/optimize", tags=["optimization"])


class OptimizeMoleculeRequest(BaseModel):
    """Request schema for lead optimization."""

    molecule_id: UUID = Field(..., description="UUID of the molecule to optimize")


class OptimizationSnapshot(BaseModel):
    """Scored details for either the original or optimized molecule."""

    smiles: str
    sas_score: float
    lipinski_pass: bool
    admet_scores: Dict[str, Any]
    docking_score: float | None = None
    combined_score: float | None = None
    molecule_id: UUID | None = None


class OptimizeMoleculeResponse(BaseModel):
    """Response schema for lead optimization."""

    original: OptimizationSnapshot
    optimized: OptimizationSnapshot
    changes: List[str]


@router.post("/molecule", response_model=OptimizeMoleculeResponse, status_code=status.HTTP_200_OK)
async def optimize_molecule(
    request: OptimizeMoleculeRequest,
    db: Session = Depends(get_db),
) -> OptimizeMoleculeResponse:
    """Optimize a stored molecule and persist the top-scoring variant."""
    try:
        result = await OptimizationService.optimize_molecule(str(request.molecule_id), db)
        return OptimizeMoleculeResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Lead optimization failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lead optimization failed",
        ) from exc
