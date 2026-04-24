"""
ADMET Router - FastAPI endpoints for ADMET prediction
"""
import logging
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from uuid import UUID

from app.database import get_db
from app.services.admet_service import ADMETService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admet", tags=["admet"])


class PredictADMETRequest(BaseModel):
    """Request schema for ADMET prediction."""
    molecule_ids: List[UUID] = Field(..., description="List of molecule UUIDs")


class ADMETScoresResponse(BaseModel):
    """ADMET scores for a single molecule."""
    bbbp_score: float | None = Field(None, ge=0, le=1)
    bbbp_traffic: str = Field(..., description="green, yellow, or red")
    hepatotoxicity_score: float | None = Field(None, ge=0, le=1)
    hepatotoxicity_traffic: str
    herg_risk: bool
    herg_confidence: float
    bioavailability_score: float = Field(..., ge=0, le=1)
    bioavailability_traffic: str
    solubility_score: float | None = Field(None, ge=0, le=1)
    solubility_traffic: str
    clearance_score: float | None = Field(None, ge=0, le=1)
    clearance_traffic: str
    cyp3a4_liability: float | None = Field(None, ge=0, le=1)
    cyp3a4_traffic: str
    model_source: str


class ADMETResultResponse(BaseModel):
    """ADMET prediction result for one molecule."""
    molecule_id: UUID
    smiles: str
    admet: ADMETScoresResponse


class PredictADMETResponse(BaseModel):
    """Response schema for ADMET prediction."""
    count: int = Field(..., description="Number of molecules predicted")
    results: List[ADMETResultResponse]


@router.post("/predict", response_model=PredictADMETResponse, status_code=status.HTTP_200_OK)
async def predict_admet(
    request: PredictADMETRequest,
    db: Session = Depends(get_db)
) -> PredictADMETResponse:
    """
    Predict ADMET properties for molecules.
    
    Predicts:
    1. BBBP (Blood-Brain Barrier Penetration) - DeepChem
    2. Hepatotoxicity (Tox21) - DeepChem
    3. hERG Cardiotoxicity - RDKit rule-based
    4. Oral Bioavailability - Rule-based
    
    Each property classified as:
    - Green: > 0.7 (good)
    - Yellow: 0.4-0.7 (moderate)
    - Red: < 0.4 (poor)
    
    Args:
        request: PredictADMETRequest with molecule_ids
        db: Database session
        
    Returns:
        PredictADMETResponse with predictions and traffic light classification
        
    Raises:
        HTTPException: If prediction fails
    """
    try:
        logger.info(f"Predicting ADMET for {len(request.molecule_ids)} molecules")
        
        # Call service
        results = await ADMETService.predict_admet_for_molecules(
            molecule_ids=[str(mol_id) for mol_id in request.molecule_ids],
            db=db
        )
        
        if not results:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid molecules to predict"
            )
        
        logger.info(f"✅ ADMET predictions complete for {len(results)} molecules")
        
        # Convert to response model
        response_results = []
        for result in results:
            response_results.append(
                ADMETResultResponse(
                    molecule_id=result["molecule_id"],
                    smiles=result["smiles"],
                    admet=ADMETScoresResponse(**result["admet"])
                )
            )
        
        return PredictADMETResponse(
            count=len(response_results),
            results=response_results
        )
        
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"ADMET prediction failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ADMET prediction failed"
        )
