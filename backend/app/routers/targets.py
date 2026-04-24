"""
Target Intelligence API Endpoints

Endpoints:
- POST /api/targets/analyze - Analyze target from natural language
- GET /api/targets/{target_id} - Get specific target
- GET /api/targets/ - List all targets
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from app.database import get_db
from app.schemas import TargetCreate, TargetResponse
from app.services.target_service import TargetEnrichmentService
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/targets", tags=["targets"])


@router.post("/analyze", response_model=TargetResponse, status_code=201)
async def analyze_target(
    request: TargetCreate,  # Can extend with query field
    db: Session = Depends(get_db)
):
    """
    Analyze and enrich a target from natural language query.
    
    Steps:
    1. Extract protein info via Gemini NLP
    2. Query UniProt for protein metadata
    3. Query ChEMBL for known drug information
    4. Query PDB for 3D structures
    5. Calculate druggability score
    6. Save to database and return
    
    Request:
    ```json
    {
        "name": "BACE1 protease in Alzheimer's disease"
    }
    ```
    
    Response:
    ```json
    {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "Beta-secretase 1",
        "uniprot_id": "P56817",
        "druggability_score": 1.0,
        "created_at": "2026-04-18T12:34:56+00:00"
    }
    ```
    """
    try:
        logger.info(f"Analyzing target: {request.name}")
        
        # Use the name field as the natural language query
        target = await TargetEnrichmentService.analyze_target(request.name, db)
        
        return TargetResponse.from_orm(target)
        
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        raise HTTPException(status_code=500, detail="Target analysis failed")


@router.get("/{target_id}", response_model=TargetResponse)
def get_target(target_id: UUID, db: Session = Depends(get_db)):
    """
    Retrieve a specific target by ID.
    
    Parameters:
    - target_id: UUID of the target
    
    Response: 200 OK with target data, or 404 if not found
    """
    logger.info(f"Retrieving target: {target_id}")
    
    target = TargetEnrichmentService.get_target(target_id, db)
    
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
    
    return TargetResponse.from_orm(target)


@router.get("/", response_model=dict)
def list_targets(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """
    List all analyzed targets with pagination.
    
    Query Parameters:
    - skip: Number of records to skip (default: 0)
    - limit: Maximum records to return (default: 100)
    
    Response:
    ```json
    {
        "count": 3,
        "skip": 0,
        "limit": 100,
        "targets": [
            {
                "id": "...",
                "name": "BACE1",
                "uniprot_id": "P56817",
                "druggability_score": 1.0,
                "created_at": "2026-04-18T12:34:56+00:00"
            },
            ...
        ]
    }
    ```
    """
    logger.info(f"Listing targets: skip={skip}, limit={limit}")
    
    targets = TargetEnrichmentService.list_targets(db, skip, limit)
    
    return {
        "count": len(targets),
        "skip": skip,
        "limit": limit,
        "targets": [TargetResponse.from_orm(t) for t in targets]
    }
