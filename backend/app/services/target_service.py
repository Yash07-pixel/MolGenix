"""
Target Enrichment Service

Orchestrates data from multiple sources (Gemini, UniProt, ChEMBL, PDB)
to create enriched drug discovery targets.
"""

import asyncio
import logging
import re
import socket
from math import log10
from typing import Any, Dict, Optional
from uuid import UUID

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ml.gemini_extractor import get_gemini_extractor
from app.models import Target
from app.schemas import TargetCreate

logger = logging.getLogger(__name__)

UNIPROT_API = "https://rest.uniprot.org/uniprotkb/search"
CHEMBL_API = "https://www.ebi.ac.uk/chembl/api/data/target/search"
CHEMBL_ACTIVITY_API = "https://www.ebi.ac.uk/chembl/api/data/activity.json"
PDB_API = "https://search.rcsb.org/rcsbsearch/v2/query"
HTTP_TIMEOUT = 30
TARGET_ALIAS_MAP = {
    "beta secretase 1": "BACE1",
    "beta secretase": "BACE1",
    "epidermal growth factor receptor": "EGFR",
    "hiv 1 protease": "HIV-1 protease",
    "cyclooxygenase 2": "COX-2",
}


class TargetEnrichmentService:
    """Service for enriching drug discovery targets with multi-source data."""

    @staticmethod
    def classify_target(
        protein_name: str,
        gene_symbol: str,
        uniprot_id: str,
        chembl_id: str,
    ) -> str:
        """
        Returns one of: kinase, protease, gpcr, nuclear_receptor,
                        ion_channel, phosphatase, cox, oxidase, other
        Uses multiple signals to classify correctly.
        """
        text = (f"{protein_name} {gene_symbol}").lower()
        gene = (gene_symbol or "").upper()

        KINASE_GENES = {
            "EGFR", "ERBB2", "ABL1", "SRC", "BRAF", "VEGFR", "KIT",
            "ALK", "MET", "RET", "JAK1", "JAK2", "CDK4", "CDK6",
            "AURKA", "AURKB", "PLK1", "CHEK1", "ATM", "ATR",
        }
        PROTEASE_GENES = {
            "BACE1", "BACE2", "ADAM10", "MMP2", "MMP9", "CASP3",
            "CASP7", "CASP9", "FURIN", "TMPRSS2", "ACE", "ACE2",
            "RENIN", "DPP4", "FAP", "PREP",
        }
        GPCR_GENES = {
            "DRD2", "DRD3", "HTR2A", "ADRB1", "ADRB2", "CHRM1",
            "CXCR4", "CCR5", "ADORA2A", "CNR1", "CNR2", "OPRM1",
        }
        COX_GENES = {"PTGS1", "PTGS2", "COX1", "COX2"}

        if gene in KINASE_GENES or "kinase" in text:
            return "kinase"
        if gene in PROTEASE_GENES or any(x in text for x in ["protease", "secretase", "peptidase", "convertase"]):
            return "protease"
        if gene in GPCR_GENES or any(x in text for x in ["gpcr", "g-protein", "g protein", "receptor coupled"]):
            return "gpcr"
        if gene in COX_GENES or "cyclooxygenase" in text:
            return "cox"
        if any(x in text for x in ["nuclear receptor", "steroid", "thyroid receptor"]):
            return "nuclear_receptor"
        if any(x in text for x in ["ion channel", "sodium channel", "potassium channel"]):
            return "ion_channel"
        if "phosphatase" in text:
            return "phosphatase"
        if "oxidase" in text:
            return "oxidase"

        logger.warning("Unknown target class for gene=%s, name=%s", gene_symbol, protein_name)
        return "other"

    @staticmethod
    def _normalize_text(value: Any) -> str:
        return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()

    @staticmethod
    def _iter_chembl_candidate_text(candidate: Dict[str, Any]) -> list[str]:
        texts = [
            candidate.get("pref_name"),
            candidate.get("target_chembl_id"),
            candidate.get("chembl_id"),
            candidate.get("target_type"),
            candidate.get("organism"),
        ]

        for component in candidate.get("target_components", []) or []:
            texts.extend(
                [
                    component.get("accession"),
                    component.get("description"),
                    component.get("component_description"),
                    component.get("component_type"),
                ]
            )
            for synonym in component.get("target_component_synonyms", []) or []:
                texts.extend(
                    [
                        synonym.get("component_synonym"),
                        synonym.get("synonym"),
                    ]
                )

        return [text for text in texts if text]

    @staticmethod
    def _score_chembl_candidate(candidate: Dict[str, Any], gene_symbol: str) -> int:
        normalized_gene = TargetEnrichmentService._normalize_text(gene_symbol)
        if not normalized_gene:
            return 0

        score = 0
        for text in TargetEnrichmentService._iter_chembl_candidate_text(candidate):
            normalized_text = TargetEnrichmentService._normalize_text(text)
            if not normalized_text:
                continue
            if normalized_text == normalized_gene:
                score += 12
            elif normalized_gene in normalized_text.split():
                score += 7
            elif normalized_gene in normalized_text:
                score += 4

        target_type = TargetEnrichmentService._normalize_text(candidate.get("target_type"))
        organism = TargetEnrichmentService._normalize_text(candidate.get("organism"))
        if "single protein" in target_type:
            score += 6
        elif "protein complex" in target_type:
            score += 2
        if "homo sapiens" in organism:
            score += 4

        return score

    @staticmethod
    def infer_target_info_from_query(query: str) -> Dict[str, str]:
        """Build a best-effort target extraction when Gemini returns empty fields."""
        normalized = (query or "").strip()
        if not normalized:
            return {"protein_name": "", "gene_symbol": "", "disease": "", "indication": ""}

        disease = ""
        if " in " in normalized.lower():
            split_index = normalized.lower().find(" in ")
            disease = normalized[split_index + 4 :].strip(" .")
            target_fragment = normalized[:split_index].strip()
        else:
            target_fragment = normalized

        normalized_target = TargetEnrichmentService._normalize_text(target_fragment)
        alias_match = TARGET_ALIAS_MAP.get(normalized_target)
        tokens = re.findall(r"[A-Za-z0-9\-]+", target_fragment)
        gene_symbol = alias_match or (tokens[0].upper() if tokens else normalized[:64])
        protein_name = target_fragment.strip() or gene_symbol

        return {
            "protein_name": protein_name,
            "gene_symbol": gene_symbol,
            "disease": disease,
            "indication": disease,
        }

    @staticmethod
    def _lookup_cached_uniprot(db: Session | None, gene_symbol: str) -> Dict[str, Any]:
        if db is None or not gene_symbol:
            return {}

        normalized_gene = TargetEnrichmentService._normalize_text(gene_symbol)
        if not normalized_gene:
            return {}

        candidates = (
            db.query(Target)
            .filter(Target.uniprot_id.isnot(None))
            .all()
        )
        for candidate in candidates:
            candidate_text = TargetEnrichmentService._normalize_text(getattr(candidate, "name", ""))
            if normalized_gene == candidate_text or normalized_gene in candidate_text.split():
                return {
                    "uniprot_id": candidate.uniprot_id,
                    "organism": getattr(candidate, "organism", "") or "",
                    "function": getattr(candidate, "function", "") or "",
                    "subcellular_location": "",
                }
        return {}

    @staticmethod
    def _apply_target_enrichment(
        target: Target,
        *,
        candidate_name: str,
        candidate_uniprot_id: Optional[str],
        druggability_score: float,
        druggability_breakdown: Dict[str, float],
        chembl_result: Dict[str, Any],
        uniprot_result: Dict[str, Any],
        pdb_result: Dict[str, Any],
        gemini_data: Dict[str, Any],
        used_gemini_result: bool,
    ) -> None:
        target.name = candidate_name or target.name
        target.uniprot_id = candidate_uniprot_id or target.uniprot_id
        target.druggability_score = druggability_score
        target.chembl_id = chembl_result.get("chembl_id")
        target.target_class = TargetEnrichmentService.classify_target(
            candidate_name or target.name or "",
            gemini_data.get("gene_symbol", "") or "",
            candidate_uniprot_id or "",
            chembl_result.get("chembl_id", "") or "",
        )
        target.known_inhibitors = chembl_result.get("known_inhibitors", 0)
        target.organism = uniprot_result.get("organism", "")
        target.function = uniprot_result.get("function", "")
        target.disease = gemini_data.get("disease", "")
        target.structure_count = pdb_result.get("structure_count", 0)
        target.pdb_id = pdb_result.get("pdb_id")
        target.druggability_breakdown = druggability_breakdown
        target.gemini_source = "gemini" if used_gemini_result else "fallback"

    @staticmethod
    async def query_uniprot(gene_symbol: str, db: Session | None = None) -> Dict[str, Any]:
        """Query UniProt API for protein information."""
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                logger.info("Querying UniProt for %s...", gene_symbol)
                response = await client.get(
                    UNIPROT_API,
                    params={"query": f"gene_exact:{gene_symbol}", "format": "json", "size": 1},
                )
                response.raise_for_status()
                data = response.json()

                if not data.get("results"):
                    logger.warning("No UniProt results for %s", gene_symbol)
                    return {}

                result = data["results"][0]
                entry_name = result.get("uniProtkbId", "")
                organism_name = ""
                function_text = ""
                location_text = ""

                if "organism" in result:
                    organism_name = result["organism"].get("scientificName", "")

                for comment in result.get("comments", []):
                    if comment.get("commentType") == "FUNCTION":
                        texts = comment.get("texts", [])
                        if texts:
                            function_text = texts[0].get("value", "")
                            break

                for feature in result.get("features", []):
                    if feature.get("type") == "SUBCELLULAR_LOCATION":
                        location_text = feature.get("description", "")
                        break

                uniprot_result = {
                    "uniprot_id": entry_name.split("_")[0] if "_" in entry_name else entry_name,
                    "organism": organism_name,
                    "function": function_text,
                    "subcellular_location": location_text,
                }

                logger.info("UniProt query successful: %s", uniprot_result["uniprot_id"])
                return uniprot_result
        except (httpx.ConnectError, socket.gaierror) as exc:
            cached = TargetEnrichmentService._lookup_cached_uniprot(db, gene_symbol)
            if cached:
                logger.warning("UniProt lookup failed for %s: %s - using cached value if available.", gene_symbol, exc)
                return cached
            logger.warning("UniProt lookup failed for %s: %s - using cached value if available.", gene_symbol, exc)
            return {"lookup_failed": True}
        except Exception as exc:
            logger.error("UniProt API error: %s", exc)
            return {}

    @staticmethod
    async def query_chembl(gene_symbol: str) -> Dict[str, Any]:
        """Query ChEMBL API for drug target information."""
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                logger.info("Querying ChEMBL for %s...", gene_symbol)
                response = await client.get(
                    CHEMBL_API,
                    params={"q": gene_symbol, "format": "json"},
                )
                response.raise_for_status()
                data = response.json()

                if not data.get("targets"):
                    logger.warning("No ChEMBL results for %s", gene_symbol)
                    return {}

                ranked_targets = sorted(
                    data["targets"],
                    key=lambda candidate: TargetEnrichmentService._score_chembl_candidate(candidate, gene_symbol),
                    reverse=True,
                )
                top_targets = ranked_targets[:3]

                async def activity_row_count(candidate: Dict[str, Any]) -> int:
                    chembl_id = candidate.get("target_chembl_id") or candidate.get("chembl_id") or ""
                    if not chembl_id:
                        return 0
                    response = await client.get(
                        CHEMBL_ACTIVITY_API,
                        params={"target_chembl_id": chembl_id, "limit": 10, "format": "json"},
                    )
                    response.raise_for_status()
                    rows = response.json().get("activities", [])
                    logger.info("ChEMBL activity query for %s returned %s rows", chembl_id, len(rows))
                    return len(rows)

                counts = await asyncio.gather(*(activity_row_count(candidate) for candidate in top_targets))
                if any(count > 0 for count in counts):
                    selected_index = max(range(len(top_targets)), key=lambda index: counts[index])
                else:
                    selected_index = 0

                target = top_targets[selected_index]
                selected_activity_count = counts[selected_index] if counts else 0
                chembl_id = target.get("target_chembl_id") or target.get("chembl_id") or ""
                chembl_result = {
                    "chembl_id": chembl_id,
                    "target_type": target.get("target_type", ""),
                    "known_inhibitors": (
                        target.get("activity_count")
                        or target.get("activities_count")
                        or target.get("molecule_count")
                        or selected_activity_count
                        or 0
                    ),
                }

                if not chembl_result["chembl_id"]:
                    logger.warning("ChEMBL search returned results for %s but no target ID could be resolved", gene_symbol)
                    return {}

                logger.info(
                    "Selected canonical ChEMBL ID %s for %s based on activity count %s",
                    chembl_result["chembl_id"],
                    gene_symbol,
                    selected_activity_count,
                )
                return chembl_result
        except Exception as exc:
            logger.error("ChEMBL API error: %s", exc)
            return {}

    @staticmethod
    async def query_pdb(gene_symbol: str) -> Dict[str, Any]:
        """Query PDB/RCSB database for 3D protein structures."""
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                logger.info("Querying PDB for %s...", gene_symbol)
                payloads = [
                    {
                        "query": {
                            "type": "terminal",
                            "service": "text",
                            "parameters": {
                                "attribute": "rcsb_entity_source_organism.rcsb_gene_name.value",
                                "operator": "exact_match",
                                "value": gene_symbol,
                            },
                        },
                        "return_type": "entry",
                        "request_options": {"paginate": {"start": 0, "rows": 10}},
                    },
                    {
                        "query": {
                            "type": "terminal",
                            "service": "text",
                            "parameters": {
                                "attribute": "struct.title",
                                "operator": "contains_words",
                                "value": gene_symbol,
                            },
                        },
                        "return_type": "entry",
                        "request_options": {"paginate": {"start": 0, "rows": 10}},
                    },
                ]

                data = {}
                for payload in payloads:
                    response = await client.post(PDB_API, json=payload)
                    if response.is_success:
                        data = response.json()
                        break
                    logger.warning("PDB search returned %s for payload %s", response.status_code, payload["query"]["parameters"]["attribute"])
                else:
                    response.raise_for_status()

                result_set = data.get("result_set", [])
                num_found = int(data.get("total_count", len(result_set)))
                pdb_result = {
                    "has_pdb_structure": num_found > 0,
                    "structure_count": num_found,
                    "pdb_id": result_set[0].get("identifier") if result_set else None,
                }

                logger.info("PDB query successful: %s structures found", num_found)
                return pdb_result
        except Exception as exc:
            logger.error("PDB API error: %s", exc)
            return {}

    @staticmethod
    def calculate_druggability_score(
        has_chembl: bool,
        known_inhibitors: int,
        organism: str,
        has_pdb: bool,
        structure_count: int = 0,
        protein_name: str = "",
        gene_symbol: str = "",
    ) -> tuple[float, Dict[str, float]]:
        """Calculate a richer druggability score and expose its component weights."""
        score = 0.0
        breakdown = {
            "chembl_evidence": 0.0,
            "inhibitor_evidence": 0.0,
            "human_relevance": 0.0,
            "structural_evidence": 0.0,
            "target_class_bonus": 0.0,
        }
        if has_chembl:
            breakdown["chembl_evidence"] = 0.25
        if known_inhibitors > 0:
            breakdown["inhibitor_evidence"] = min(0.3, 0.08 + log10(known_inhibitors + 1) * 0.12)
        if organism and "homo sapiens" in organism.lower():
            breakdown["human_relevance"] = 0.15
        if has_pdb:
            breakdown["structural_evidence"] = min(0.2, 0.08 + log10(max(1, structure_count)) * 0.05)
        target_text = f"{protein_name} {gene_symbol}".lower()
        if any(keyword in target_text for keyword in ["kinase", "protease", "receptor", "cyclooxygenase", "secretase"]):
            breakdown["target_class_bonus"] = 0.1
        score = sum(breakdown.values())
        score = min(score, 1.0)
        rounded_breakdown = {key: round(value, 4) for key, value in breakdown.items()}
        logger.info("Calculated druggability score: %s (%s)", score, rounded_breakdown)
        return round(score, 4), rounded_breakdown

    @staticmethod
    async def analyze_target(query: str, db: Session) -> Target:
        """Analyze and enrich a target from a natural language query."""
        logger.info("Starting target analysis for query: %s", query)

        extractor = get_gemini_extractor()
        gemini_data = extractor.extract_target_info(query)
        used_gemini_result = bool(gemini_data.get("gene_symbol") or gemini_data.get("protein_name"))
        if not gemini_data.get("gene_symbol") and not gemini_data.get("protein_name"):
            fallback_data = TargetEnrichmentService.infer_target_info_from_query(query)
            logger.warning("Gemini returned empty target fields, using query fallback: %s", fallback_data)
            gemini_data = fallback_data

        gene_symbol = gemini_data.get("gene_symbol")
        protein_name = gemini_data.get("protein_name", "")
        if not gene_symbol:
            gene_symbol = protein_name or query.strip()
        if not protein_name:
            protein_name = gene_symbol or query.strip()

        logger.info("Extracted gene_symbol=%s, protein_name=%s", gene_symbol, protein_name)

        logger.info("Querying external APIs in parallel...")
        uniprot_result, chembl_result, pdb_result = await asyncio.gather(
            TargetEnrichmentService.query_uniprot(gene_symbol, db),
            TargetEnrichmentService.query_chembl(gene_symbol),
            TargetEnrichmentService.query_pdb(gene_symbol),
            return_exceptions=True,
        )

        uniprot_result = uniprot_result if isinstance(uniprot_result, dict) else {}
        chembl_result = chembl_result if isinstance(chembl_result, dict) else {}
        pdb_result = pdb_result if isinstance(pdb_result, dict) else {}

        druggability_score, druggability_breakdown = TargetEnrichmentService.calculate_druggability_score(
            has_chembl=bool(chembl_result.get("chembl_id")),
            known_inhibitors=chembl_result.get("known_inhibitors", 0),
            organism=uniprot_result.get("organism", ""),
            has_pdb=pdb_result.get("has_pdb_structure", False),
            structure_count=pdb_result.get("structure_count", 0),
            protein_name=protein_name,
            gene_symbol=gene_symbol,
        )

        logger.info("Saving target to database...")
        candidate_uniprot_id = uniprot_result.get("uniprot_id")
        candidate_name = protein_name or gene_symbol
        if uniprot_result.get("lookup_failed") and not candidate_uniprot_id:
            logger.error("UniProt has no cached result for %s; uniprot_id will be stored as None", gene_symbol)

        existing_target = None
        if candidate_uniprot_id:
            existing_target = db.query(Target).filter(Target.uniprot_id == candidate_uniprot_id).first()
        if existing_target is None and candidate_name:
            existing_target = db.query(Target).filter(Target.name == candidate_name).first()

        if existing_target is not None:
            TargetEnrichmentService._apply_target_enrichment(
                existing_target,
                candidate_name=candidate_name,
                candidate_uniprot_id=candidate_uniprot_id,
                druggability_score=druggability_score,
                druggability_breakdown=druggability_breakdown,
                chembl_result=chembl_result,
                uniprot_result=uniprot_result,
                pdb_result=pdb_result,
                gemini_data=gemini_data,
                used_gemini_result=used_gemini_result,
            )
            db.commit()
            db.refresh(existing_target)
            logger.info("Reused existing target with ID: %s", existing_target.id)
            return existing_target

        target_data = TargetCreate(
            name=candidate_name,
            uniprot_id=candidate_uniprot_id,
            druggability_score=druggability_score,
        )

        db_target = Target(**target_data.dict())
        db.add(db_target)
        try:
            db.commit()
            db.refresh(db_target)
            TargetEnrichmentService._apply_target_enrichment(
                db_target,
                candidate_name=candidate_name,
                candidate_uniprot_id=candidate_uniprot_id,
                druggability_score=druggability_score,
                druggability_breakdown=druggability_breakdown,
                chembl_result=chembl_result,
                uniprot_result=uniprot_result,
                pdb_result=pdb_result,
                gemini_data=gemini_data,
                used_gemini_result=used_gemini_result,
            )
            db.commit()
            db.refresh(db_target)
            logger.info("Target saved with ID: %s", db_target.id)
            return db_target
        except IntegrityError:
            db.rollback()
            fallback_target = None
            if target_data.uniprot_id:
                fallback_target = db.query(Target).filter(Target.uniprot_id == target_data.uniprot_id).first()
            if fallback_target is None:
                fallback_target = db.query(Target).filter(Target.name == target_data.name).first()
            if fallback_target is None:
                raise
            TargetEnrichmentService._apply_target_enrichment(
                fallback_target,
                candidate_name=candidate_name,
                candidate_uniprot_id=candidate_uniprot_id,
                druggability_score=druggability_score,
                druggability_breakdown=druggability_breakdown,
                chembl_result=chembl_result,
                uniprot_result=uniprot_result,
                pdb_result=pdb_result,
                gemini_data=gemini_data,
                used_gemini_result=used_gemini_result,
            )
            db.commit()
            db.refresh(fallback_target)
            logger.info("Recovered existing target after integrity conflict: %s", fallback_target.id)
            return fallback_target

    @staticmethod
    def get_target(target_id: UUID, db: Session) -> Optional[Target]:
        """Retrieve target by ID."""
        return db.query(Target).filter(Target.id == target_id).first()

    @staticmethod
    def list_targets(db: Session, skip: int = 0, limit: int = 100) -> list[Target]:
        """List all targets with pagination."""
        return db.query(Target).offset(skip).limit(limit).all()
