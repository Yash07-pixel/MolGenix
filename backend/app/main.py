from pathlib import Path
import re
from typing import Any, Dict, List

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
from pydantic import BaseModel, Field

from app.config import settings
from app.database import get_db, init_db, engine
from sqlalchemy.orm import Session
from app.routers import targets_router, molecules_router, admet_router, docking_router, optimization_router, reports_router
from app.models.target import Target
from app.models.target_context import TargetContext
from app.services.admet_service import ADMETService
from app.services.docking_service import DockingService
from app.services.molecule_service import MoleculeGenerationService
from app.services.optimization_service import OptimizationService
from app.services.report_service import ReportService
from app.services.target_service import TargetEnrichmentService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


OPENAPI_TAGS = [
    {"name": "targets", "description": "Target discovery and enrichment endpoints."},
    {"name": "molecules", "description": "Molecule generation and retrieval endpoints."},
    {"name": "admet", "description": "ADMET prediction and traffic-light classification endpoints."},
    {"name": "docking", "description": "Docking execution and ranked docking result endpoints."},
    {"name": "optimization", "description": "Lead optimization endpoints for rescoring improved variants."},
    {"name": "reports", "description": "PDF report generation and download endpoints."},
    {"name": "pipeline", "description": "End-to-end orchestration endpoints for the full MolGenix workflow."},
    {"name": "system", "description": "Health and root metadata endpoints."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    logger.info("🧬 MolGenix Backend Starting Up...")
    logger.info(f"Database: {settings.DATABASE_URL}")
    logger.info(f"Gemini API configured: {bool(settings.GEMINI_API_KEY)}")
    
    # Initialize database tables
    try:
        init_db()
        logger.info("✅ Database tables initialized")
    except Exception as e:
        logger.error(f"⚠️  Database initialization warning: {e}")
    
    yield
    logger.info("🧬 MolGenix Backend Shutting Down...")


# Initialize FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-Powered Drug Discovery Backend",
    lifespan=lifespan,
    openapi_tags=OPENAPI_TAGS,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(targets_router)
app.include_router(molecules_router)
app.include_router(admet_router)
app.include_router(docking_router)
app.include_router(optimization_router)
app.include_router(reports_router)


class PipelineRunRequest(BaseModel):
    """Request schema for the full end-to-end discovery pipeline."""

    query: str = Field(..., min_length=1, description="Natural-language target discovery query")
    seed_smiles: str | None = Field(
        None,
        description="Optional seed molecule SMILES. If omitted, MolGenix fetches known target-related compounds from ChEMBL.",
    )
    n_molecules: int = Field(10, ge=1, le=1000, description="Number of molecules to generate")


TARGET_PDB_HINTS = {
    "bace1": ["2qmg.pdb"],
    "beta-secretase": ["2qmg.pdb"],
    "egfr": ["1iep.pdb"],
    "epidermal growth factor receptor": ["1iep.pdb"],
    "hiv": ["1hvr.pdb"],
    "hiv-1 protease": ["1hvr.pdb"],
    "protease": ["1hvr.pdb"],
    "cox-2": ["1cx2.pdb"],
    "cyclooxygenase": ["1cx2.pdb"],
    "ptgs2": ["1cx2.pdb"],
}


def _normalize_target_text(*parts: str | None) -> str:
    text = " ".join(part for part in parts if part).strip().lower()
    return re.sub(r"[^a-z0-9\-\s]+", " ", text)


def _find_default_pdb_filename(target: Any | None = None, query: str | None = None) -> str | None:
    pdb_dir = Path(settings.PDB_STORAGE_PATH)
    pdb_files = sorted(pdb_dir.glob("*.pdb"))
    if not pdb_files:
        logger.warning("No receptor PDB files found in %s; pipeline will use mock docking scores", pdb_dir)
        return None

    available_by_lower = {path.name.lower(): path.name for path in pdb_files}
    target_text = _normalize_target_text(
        getattr(target, "name", None) if target is not None else None,
        getattr(target, "uniprot_id", None) if target is not None else None,
        query,
    )

    for hint, candidates in TARGET_PDB_HINTS.items():
        if hint in target_text:
            for candidate in candidates:
                if candidate.lower() in available_by_lower:
                    selected = available_by_lower[candidate.lower()]
                    logger.info("Selected receptor %s for target text '%s' using hint '%s'", selected, target_text, hint)
                    return selected

    selected = pdb_files[0].name
    logger.warning(
        "No target-specific receptor mapping found for '%s'; defaulting to %s",
        target_text or "unknown target",
        selected,
    )
    return selected


def _admet_green_count(admet_scores: Dict[str, Any]) -> int:
    return sum(
        [
            admet_scores.get("bbbp_traffic") == "green",
            admet_scores.get("hepatotoxicity_traffic") == "green",
            not admet_scores.get("herg_risk", False),
            admet_scores.get("bioavailability_traffic") == "green",
            admet_scores.get("solubility_traffic") == "green",
            admet_scores.get("clearance_traffic") == "green",
            admet_scores.get("cyp3a4_traffic") == "green",
        ]
    )


def _combined_score(sas_score: float | None, lipinski_pass: bool, admet_scores: Dict[str, Any]) -> float:
    safe_sas = sas_score if sas_score is not None else 10.0
    return round(
        (1 - safe_sas / 10.0) * 0.4
        + float(lipinski_pass) * 0.3
        + (_admet_green_count(admet_scores) / 7.0) * 0.3,
        4,
    )


def _molecule_weight(molecule: Any) -> float:
    metadata = molecule.admet_scores if isinstance(molecule.admet_scores, dict) else {}
    try:
        return float(metadata.get("molecular_weight", float("inf")))
    except (TypeError, ValueError):
        return float("inf")


def _serialize_target(target: Any) -> Dict[str, Any]:
    return {
        "id": str(target.id),
        "name": target.name,
        "uniprot_id": target.uniprot_id,
        "druggability_score": target.druggability_score,
        "chembl_id": getattr(target, "chembl_id", None),
        "target_class": getattr(target, "target_class", None),
        "disease": getattr(target, "disease", None),
        "known_inhibitors": getattr(target, "known_inhibitors", None),
        "structure_count": getattr(target, "structure_count", None),
        "pdb_id": getattr(target, "pdb_id", None),
        "gemini_source": getattr(target, "gemini_source", None),
        "druggability_breakdown": getattr(target, "druggability_breakdown", None),
        "pipeline_complete": getattr(target, "pipeline_complete", False),
        "pipeline_error": getattr(target, "pipeline_error", None),
        "created_at": target.created_at.isoformat(),
    }


def _coerce_known_inhibitors(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, dict):
        for key in ("count", "total", "known_inhibitors"):
            nested = value.get(key)
            if isinstance(nested, (int, float)):
                return int(nested)
    return 0


def _build_target_context(target: Target, query: str) -> TargetContext:
    inferred = TargetEnrichmentService.infer_target_info_from_query(query)
    gene_symbol = (
        getattr(target, "gene_symbol", None)
        or inferred.get("gene_symbol")
        or target.name
    )
    receptor_filename = _find_default_pdb_filename(target=target, query=query)
    receptor_pdb_path = str(Path(settings.PDB_STORAGE_PATH) / receptor_filename) if receptor_filename else None
    return TargetContext(
        target_id=str(target.id),
        gene_symbol=str(gene_symbol or ""),
        protein_name=str(target.name or inferred.get("protein_name") or gene_symbol or ""),
        disease=str(getattr(target, "disease", None) or inferred.get("disease") or ""),
        uniprot_id=str(getattr(target, "uniprot_id", None) or ""),
        chembl_id=str(getattr(target, "chembl_id", None) or ""),
        pdb_id=str(getattr(target, "pdb_id", None) or (Path(receptor_filename).stem.upper() if receptor_filename else "")),
        function=str(getattr(target, "function", None) or ""),
        known_inhibitors=_coerce_known_inhibitors(getattr(target, "known_inhibitors", None)),
        druggability_score=float(getattr(target, "druggability_score", None) or 0.0),
        target_class=str(getattr(target, "target_class", None) or "other"),
        receptor_pdb_path=receptor_pdb_path,
        docking_center=None,
        docking_box_size=(DockingService.BOX_SIZE, DockingService.BOX_SIZE, DockingService.BOX_SIZE),
    )


def _set_pipeline_status(
    db: Session,
    target: Target,
    *,
    pipeline_complete: bool,
    pipeline_error: str | None = None,
) -> None:
    target.pipeline_complete = pipeline_complete
    target.pipeline_error = pipeline_error
    db.add(target)
    db.commit()
    db.refresh(target)


def _serialize_molecule(molecule: Any, admet_scores: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(molecule.id),
        "target_id": str(molecule.target_id),
        "smiles": molecule.smiles,
        "lipinski_pass": molecule.lipinski_pass,
        "sas_score": molecule.sas_score,
        "admet_scores": admet_scores,
        "docking_score": molecule.docking_score,
        "is_optimized": molecule.is_optimized,
        "created_at": molecule.created_at.isoformat(),
        "combined_score": _combined_score(molecule.sas_score, molecule.lipinski_pass, admet_scores),
    }


@app.post(
    "/api/pipeline/run",
    tags=["pipeline"],
    status_code=status.HTTP_200_OK,
    summary="Run the full MolGenix discovery pipeline",
    description=(
        "Analyze a target, generate molecules, predict ADMET, dock the top leads, optimize the best "
        "molecule, and generate a PDF report in a single orchestration call."
    ),
)
async def run_pipeline(
    request: PipelineRunRequest,
    db: Session = Depends(get_db),
):
    target: Target | None = None
    # FIXED
    target_context: TargetContext | None = None
    try:
        # FIXED
        analyzed_target = await TargetEnrichmentService.analyze_target(request.query, db)
        # FIXED
        target = db.query(Target).filter(Target.id == analyzed_target.id).first()
        # FIXED
        if not target:
            # FIXED
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found")

        # FIXED
        gene_symbol = getattr(target, "gene_symbol", None) or ((target.name or "").split()[0].upper() if target.name else "")
        # FIXED
        known_inhibitors = getattr(target, "known_inhibitors", None) or []
        # FIXED
        if isinstance(known_inhibitors, int):
            # FIXED
            known_inhibitor_count = known_inhibitors
        # FIXED
        elif isinstance(known_inhibitors, dict):
            # FIXED
            known_inhibitor_count = len(known_inhibitors)
        # FIXED
        else:
            # FIXED
            known_inhibitor_count = len(known_inhibitors)

        # FIXED
        target_context = TargetContext(
            target_id=str(target.id),
            gene_symbol=gene_symbol or "",
            protein_name=target.name,
            disease=target.disease or "",
            uniprot_id=target.uniprot_id or "",
            chembl_id=target.chembl_id or "",
            pdb_id=target.pdb_id or "",
            function=target.function or "",
            known_inhibitors=known_inhibitor_count,
            druggability_score=target.druggability_score or 0.0,
        )

        # FIXED
        target.pipeline_complete = False
        # FIXED
        target.pipeline_error = None
        # FIXED
        db.add(target)
        # FIXED
        db.commit()
        # FIXED
        db.refresh(target)

        # FIXED
        molecules, _valid_count = await MoleculeGenerationService.generate_molecules(
            target_context,
            db,
            seed_smiles=request.seed_smiles,
            n_molecules=request.n_molecules,
        )
        # FIXED
        if not molecules:
            # FIXED
            raise ValueError("No molecules generated")

        # FIXED
        admet_results = await ADMETService.score_molecules(
            target_context,
            molecules,
            db,
        )
        # FIXED
        docking_results = await DockingService.dock_molecules(
            target_context,
            molecules,
            db,
        )

        # FIXED
        molecules_by_weight = sorted(molecules, key=_molecule_weight)
        # FIXED
        best_molecule_id = (
            min(docking_results, key=lambda result: result["docking_score"])["molecule_id"]
            if docking_results
            else str(molecules_by_weight[0].id)
        )
        # FIXED
        optimization = await OptimizationService.optimize_molecule(best_molecule_id, db)
        # FIXED
        report = await ReportService.generate_report(target_context, molecules, db)

        # FIXED
        target.pipeline_complete = True
        # FIXED
        target.pipeline_error = None
        # FIXED
        db.add(target)
        # FIXED
        db.commit()
        # FIXED
        db.refresh(target)

        # FIXED
        return {
            "status": "success",
            "target_id": str(target.id),
            "molecules": [str(molecule.id) for molecule in molecules],
            "docking_results": docking_results,
            "report_id": report.get("report_id"),
            "receptor_used": target_context.receptor_pdb_path,
            "is_mock_docking": target_context.receptor_pdb_path is None,
            "optimized_lead": optimization.get("optimized"),
            "admet_results": admet_results,
        }
    except Exception as exc:
        logger.error("Pipeline execution failed: %s", exc)
        if target is not None:
            try:
                db.rollback()
                # FIXED
                target.pipeline_complete = False
                # FIXED
                target.pipeline_error = str(exc)
                # FIXED
                db.add(target)
                # FIXED
                db.commit()
                # FIXED
                db.refresh(target)
            except Exception as status_exc:
                logger.error("Failed to persist pipeline error status: %s", status_exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@app.get(
    "/api/targets/{target_id}/status",
    tags=["targets"],
    status_code=status.HTTP_200_OK,
    summary="Get target pipeline status",
    description="Return pipeline completion state and the last pipeline error for a target.",
)
async def get_target_pipeline_status(
    target_id: str,
    db: Session = Depends(get_db),
):
    target = db.query(Target).filter(Target.id == target_id).first()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found")

    return {
        "target_id": str(target.id),
        "pipeline_complete": bool(getattr(target, "pipeline_complete", False)),
        "pipeline_error": getattr(target, "pipeline_error", None),
    }


@app.get("/health", tags=["system"], summary="Health check", description="Simple liveness probe for the backend.")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/", tags=["system"], summary="API root", description="Root metadata endpoint for the MolGenix backend.")
async def root():
    """Root endpoint."""
    return {
        "message": "Welcome to MolGenix 🧬",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )
