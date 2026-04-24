"""
Molecules Router - FastAPI endpoints for molecule generation and retrieval
"""
import io
import logging
from pathlib import Path
from typing import Any, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.molecule import Molecule
from app.schemas.molecule import MoleculeResponse
from app.services.gemini_service import GeminiService
from app.services.molecule_service import MoleculeGenerationService

try:
    from rdkit import Chem
    from rdkit.Chem import Draw

    RDKIT_AVAILABLE = True
except ImportError:
    Chem = None
    Draw = None
    RDKIT_AVAILABLE = False

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/molecules", tags=["molecules"])

IMAGE_CACHE_DIR = Path("/tmp/mol_images")


class GenerateMoleculesRequest(BaseModel):
    """Request schema for molecule generation."""

    target_id: UUID = Field(..., description="UUID of target")
    seed_smiles: str = Field(..., max_length=2048, description="Seed SMILES string")
    n_molecules: int = Field(20, ge=1, le=1000, description="Number of molecules to generate")


class GenerateMoleculesResponse(BaseModel):
    """Response schema for molecule generation."""

    count: int = Field(..., description="Total molecules generated")
    valid_count: int = Field(..., description="Molecules passing Lipinski")
    target_id: UUID
    molecules: List[MoleculeResponse]


class ListMoleculesResponse(BaseModel):
    """Response schema for listing molecules."""

    count: int
    target_id: UUID
    skip: int
    limit: int
    molecules: List[MoleculeResponse]


class BatchMoleculesResponse(BaseModel):
    """Response schema for fetching molecules by explicit IDs."""

    count: int
    molecules: List[MoleculeResponse]


class MoleculeRationaleResponse(BaseModel):
    """Response schema for molecule rationale."""

    rationale: str


class MoleculeOptimizationResponse(BaseModel):
    """Response schema for molecule optimization provenance."""

    changes: List[str]
    is_optimized: bool


def _get_molecule_or_404(molecule_id: UUID, db: Session) -> Molecule:
    molecule = db.query(Molecule).filter(Molecule.id == molecule_id).first()
    if not molecule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Molecule not found",
        )
    return molecule


def _molecule_cache_path(molecule_id: UUID) -> Path:
    return IMAGE_CACHE_DIR / f"{molecule_id}.png"


def _serialize_molecule(molecule: Molecule) -> MoleculeResponse:
    return MoleculeResponse(
        id=molecule.id,
        target_id=molecule.target_id,
        smiles=molecule.smiles,
        lipinski_pass=molecule.lipinski_pass,
        sas_score=molecule.sas_score,
        admet_scores=molecule.admet_scores,
        docking_score=molecule.docking_score,
        is_optimized=molecule.is_optimized,
        created_at=molecule.created_at,
    )


def _summarize_admet_scores(admet_scores: Any) -> str:
    if not isinstance(admet_scores, dict) or not admet_scores:
        return "no ADMET data available"

    summary_parts: List[str] = []
    for key, value in admet_scores.items():
        if key.startswith("_"):
            continue
        label = key.replace("_", " ")
        if isinstance(value, float):
            summary_parts.append(f"{label} {value:.2f}")
        else:
            summary_parts.append(f"{label} {value}")

    return ", ".join(summary_parts[:5]) if summary_parts else "no ADMET data available"


def _fallback_rationale(docking_score: float | None, admet_scores: Any) -> str:
    return (
        f"This molecule has a docking score of {docking_score} kcal/mol. "
        f"ADMET profile: {_summarize_admet_scores(admet_scores)}. "
        "Further experimental validation is recommended."
    )


def _build_rationale_prompt(smiles: str, admet_scores: Any, docking_score: float | None) -> str:
    return (
        "You are a medicinal chemist. Given this drug candidate:\n"
        f"SMILES: {smiles}\n"
        f"ADMET scores: {admet_scores}\n"
        f"Docking score: {docking_score} kcal/mol\n"
        "Write exactly 3 sentences explaining why this molecule is or is not a \n"
        "promising drug candidate. Be specific about the numerical scores. \n"
        "Do not use jargon."
    )


def _generate_rationale_text(smiles: str, admet_scores: Any, docking_score: float | None) -> str:
    prompt = _build_rationale_prompt(smiles, admet_scores, docking_score)
    response_text = GeminiService._post_prompt(prompt)
    if response_text and response_text.strip():
        return response_text.strip()
    return _fallback_rationale(docking_score, admet_scores)


@router.post("/generate", response_model=GenerateMoleculesResponse, status_code=status.HTTP_201_CREATED)
async def generate_molecules(
    request: GenerateMoleculesRequest,
    db: Session = Depends(get_db),
) -> GenerateMoleculesResponse:
    """
    Generate molecular variants for a target.

    Pipeline:
    1. Generate N variants from seed SMILES using RDKit
    2. Validate with Lipinski Rule of Five
    3. Calculate Synthetic Accessibility (SAS) score
    4. Save to database
    5. Return created molecules
    """
    try:
        molecules, valid_count = await MoleculeGenerationService.generate_molecules_for_target(
            target_id=str(request.target_id),
            seed_smiles=request.seed_smiles,
            n_molecules=request.n_molecules,
            db=db,
        )

        logger.info("Generated %s molecules for target %s", len(molecules), request.target_id)

        return GenerateMoleculesResponse(
            count=len(molecules),
            valid_count=valid_count,
            target_id=request.target_id,
            molecules=[_serialize_molecule(molecule) for molecule in molecules],
        )
    except ValueError as exc:
        logger.error("Validation error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("Molecule generation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Molecule generation failed",
        ) from exc


@router.get("/batch", response_model=BatchMoleculesResponse)
async def get_molecules_batch(
    ids: List[UUID] = Query(...),
    db: Session = Depends(get_db),
) -> BatchMoleculesResponse:
    """Return only the exact molecules requested by ID, skipping any missing IDs."""
    try:
        molecules = MoleculeGenerationService.get_molecules_by_ids([str(molecule_id) for molecule_id in ids], db)
        return BatchMoleculesResponse(
            count=len(molecules),
            molecules=[_serialize_molecule(molecule) for molecule in molecules],
        )
    except Exception as exc:
        logger.error("Failed to retrieve molecule batch: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve molecule batch",
        ) from exc


@router.get("/{molecule_id}/image")
async def get_molecule_image(
    molecule_id: UUID,
    db: Session = Depends(get_db),
):
    """Return a cached or freshly generated PNG image for a molecule."""
    molecule = _get_molecule_or_404(molecule_id, db)

    if not RDKIT_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RDKit is required to generate molecule images",
        )

    mol = Chem.MolFromSmiles(molecule.smiles)
    if mol is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid SMILES",
        )

    cache_path = _molecule_cache_path(molecule_id)
    try:
        if not cache_path.exists():
            IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            image = Draw.MolToImage(mol, size=(400, 300))
            image.save(cache_path, format="PNG")

        return StreamingResponse(
            io.BytesIO(cache_path.read_bytes()),
            media_type="image/png",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to render molecule image for %s: %s", molecule_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate molecule image",
        ) from exc


@router.get("/{molecule_id}/rationale", response_model=MoleculeRationaleResponse)
async def get_molecule_rationale(
    molecule_id: UUID,
    db: Session = Depends(get_db),
) -> MoleculeRationaleResponse:
    """Return a plain-English rationale for a molecule."""
    molecule = _get_molecule_or_404(molecule_id, db)

    cached_rationale = getattr(molecule, "rationale", None)
    if isinstance(cached_rationale, str) and cached_rationale.strip():
        return MoleculeRationaleResponse(rationale=cached_rationale.strip())

    admet_scores = molecule.admet_scores if isinstance(molecule.admet_scores, dict) else {}

    try:
        rationale = _generate_rationale_text(
            molecule.smiles,
            admet_scores,
            molecule.docking_score,
        )
    except Exception as exc:
        logger.warning("Gemini rationale generation failed for %s: %s", molecule_id, exc)
        rationale = _fallback_rationale(molecule.docking_score, admet_scores)

    if "rationale" in Molecule.__table__.columns.keys():
        try:
            molecule.rationale = rationale
            db.add(molecule)
            db.commit()
            db.refresh(molecule)
        except Exception as exc:
            logger.warning("Failed to persist rationale for %s: %s", molecule_id, exc)
            db.rollback()
    else:
        logger.info("Molecule rationale column is not present; returning non-persisted rationale for %s", molecule_id)

    return MoleculeRationaleResponse(rationale=rationale)


@router.get("/{molecule_id}/optimization", response_model=MoleculeOptimizationResponse)
async def get_molecule_optimization(
    molecule_id: UUID,
    db: Session = Depends(get_db),
) -> MoleculeOptimizationResponse:
    """Return persisted optimization changes for a molecule."""
    molecule = _get_molecule_or_404(molecule_id, db)
    changes = molecule.optimization_changes if isinstance(molecule.optimization_changes, list) else []
    if not molecule.is_optimized:
        changes = []
    return MoleculeOptimizationResponse(
        changes=changes,
        is_optimized=bool(molecule.is_optimized),
    )


@router.get("/{target_id}", response_model=ListMoleculesResponse)
async def get_molecules_for_target(
    target_id: UUID,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> ListMoleculesResponse:
    """Get all molecules for a target."""
    try:
        if skip < 0 or limit < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid pagination parameters",
            )

        molecules = MoleculeGenerationService.get_molecules_for_target(
            target_id=str(target_id),
            db=db,
            skip=skip,
            limit=limit,
        )
        total_count = MoleculeGenerationService.get_molecules_count(
            target_id=str(target_id),
            db=db,
        )

        return ListMoleculesResponse(
            count=total_count,
            target_id=target_id,
            skip=skip,
            limit=limit,
            molecules=[_serialize_molecule(molecule) for molecule in molecules],
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to retrieve molecules: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve molecules",
        ) from exc
