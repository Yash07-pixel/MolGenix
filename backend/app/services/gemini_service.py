"""
Centralized Gemini service using the REST API.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from collections import OrderedDict
from json import JSONDecodeError
from typing import Any, Dict, Tuple

try:
    import requests
except ImportError:
    class _RequestsShim:
        class RequestException(Exception):
            pass

        @staticmethod
        def post(*args, **kwargs):
            raise RuntimeError("requests is not installed")

    requests = _RequestsShim()

try:
    from app.config import settings
except Exception:
    class _FallbackSettings:
        GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
        GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        GEMINI_MAX_RETRIES = int(os.getenv("GEMINI_MAX_RETRIES", "3"))

    settings = _FallbackSettings()

logger = logging.getLogger(__name__)


class GeminiService:
    """Shared wrapper for Gemini REST calls with safe fallbacks."""

    API_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    TIMEOUT = 30
    CACHE_MAX_ENTRIES = 100
    _response_cache: "OrderedDict[str, str]" = OrderedDict()
    _rate_limited_until = 0.0

    @staticmethod
    def _cache_enabled() -> bool:
        return os.getenv("GEMINI_CACHE_ENABLED", "True").strip().lower() != "false"

    @staticmethod
    def _max_retries() -> int:
        return max(0, int(getattr(settings, "GEMINI_MAX_RETRIES", 3)))

    @staticmethod
    def _cooldown_seconds() -> int:
        return max(0, int(os.getenv("GEMINI_RATE_LIMIT_COOLDOWN_SECONDS", "600")))

    @staticmethod
    def _cache_key(prompt: str) -> str:
        return hashlib.md5(prompt.encode("utf-8")).hexdigest()

    @staticmethod
    def _get_cached_response(prompt: str) -> str | None:
        if not GeminiService._cache_enabled():
            return None
        key = GeminiService._cache_key(prompt)
        cached = GeminiService._response_cache.get(key)
        if cached is None:
            return None
        GeminiService._response_cache.move_to_end(key)
        logger.info("Gemini response served from cache for prompt hash %s", key[:12])
        return cached

    @staticmethod
    def _set_cached_response(prompt: str, response_text: str) -> None:
        if not GeminiService._cache_enabled() or not response_text:
            return
        key = GeminiService._cache_key(prompt)
        GeminiService._response_cache[key] = response_text
        GeminiService._response_cache.move_to_end(key)
        while len(GeminiService._response_cache) > GeminiService.CACHE_MAX_ENTRIES:
            GeminiService._response_cache.popitem(last=False)

    @staticmethod
    def _sleep_for_retry(attempt_number: int) -> None:
        delay_seconds = min(2 ** attempt_number, 8)
        logger.warning("Gemini retry backoff: sleeping for %s seconds", delay_seconds)
        time.sleep(delay_seconds)

    @staticmethod
    def _in_rate_limit_cooldown() -> bool:
        return time.time() < GeminiService._rate_limited_until

    @staticmethod
    def _activate_rate_limit_cooldown() -> None:
        cooldown_seconds = GeminiService._cooldown_seconds()
        if cooldown_seconds <= 0:
            return
        GeminiService._rate_limited_until = time.time() + cooldown_seconds
        logger.warning(
            "Gemini cooldown activated for %s seconds after repeated 429 responses",
            cooldown_seconds,
        )

    @staticmethod
    def _infer_target_info(query: str) -> Dict[str, Any]:
        normalized_query = (query or "").strip()
        if not normalized_query:
            return {
                "protein_name": "",
                "gene_symbol": "",
                "disease": "",
                "indication": "",
            }

        gene_match = re.search(r"\b([A-Z0-9]{2,6})\b", normalized_query)
        gene_symbol = gene_match.group(1) if gene_match else ""

        disease = ""
        disease_match = re.search(r"\b(?:in|for|against)\s+(.+)$", normalized_query, flags=re.IGNORECASE)
        if disease_match:
            disease = disease_match.group(1).strip(" .,:;")

        protein_name = normalized_query
        if disease_match:
            protein_name = normalized_query[: disease_match.start()].strip(" .,:;")

        if not protein_name:
            protein_name = normalized_query

        return {
            "protein_name": protein_name,
            "gene_symbol": gene_symbol,
            "disease": disease,
            "indication": disease,
        }

    @staticmethod
    def _post_prompt(prompt: str) -> str:
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        logger.info("Gemini prompt: %s", prompt)

        cached = GeminiService._get_cached_response(prompt)
        if cached is not None:
            return cached

        if GeminiService._in_rate_limit_cooldown():
            remaining_seconds = int(max(0, GeminiService._rate_limited_until - time.time()))
            logger.warning(
                "Skipping Gemini API call because rate-limit cooldown is active for %s more seconds",
                remaining_seconds,
            )
            return ""

        if not settings.GEMINI_API_KEY:
            logger.warning("GEMINI_API_KEY not configured")
            return ""

        api_url = GeminiService.API_URL_TEMPLATE.format(model=settings.GEMINI_MODEL)
        max_retries = GeminiService._max_retries()

        for attempt in range(max_retries + 1):
            try:
                response = requests.post(
                    api_url,
                    headers={"x-goog-api-key": settings.GEMINI_API_KEY},
                    json=payload,
                    timeout=GeminiService.TIMEOUT,
                )
                response.raise_for_status()
                response_json = response.json()
                GeminiService._rate_limited_until = 0.0
                logger.info("Gemini response payload: %s", response_json)
                text = (
                    response_json.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", "")
                    .strip()
                )
                if text:
                    GeminiService._set_cached_response(prompt, text)
                return text
            except requests.RequestException as exc:
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                is_retryable = status_code in {429, 500, 502, 503, 504}
                if is_retryable and attempt < max_retries:
                    logger.warning(
                        "Gemini API request failed with status %s; retrying (%s/%s)",
                        status_code,
                        attempt + 1,
                        max_retries,
                    )
                    GeminiService._sleep_for_retry(attempt + 1)
                    continue
                if status_code == 429:
                    logger.warning("Gemini rate-limited after %s retries, using fallback.", max_retries)
                    GeminiService._activate_rate_limit_cooldown()
                    return ""
                logger.error("Gemini API request failed: %s", exc)
                return ""
            except (ValueError, KeyError, IndexError) as exc:
                logger.error("Gemini API response parsing failed: %s", exc)
                return ""
            except Exception as exc:
                logger.error("Unexpected Gemini API error: %s", exc)
                return ""

        return ""

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            pieces = cleaned.split("```")
            if len(pieces) >= 2:
                cleaned = pieces[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
        return cleaned.strip()

    @staticmethod
    def extract_target_info(query: str) -> Dict[str, Any]:
        prompt = (
            f"Extract the protein target, gene symbol, and disease from this query: '{query}'.\n"
            "Return JSON only: { protein_name, gene_symbol, disease, indication }"
        )

        raw_text = GeminiService._post_prompt(prompt)
        if not raw_text:
            return GeminiService._infer_target_info(query)

        try:
            parsed = json.loads(GeminiService._strip_code_fences(raw_text))
            result = {
                "protein_name": parsed.get("protein_name", "") or "",
                "gene_symbol": parsed.get("gene_symbol", "") or "",
                "disease": parsed.get("disease", "") or "",
                "indication": parsed.get("indication", "") or "",
            }
            if not any(result.values()):
                return GeminiService._infer_target_info(query)
            logger.info("extract_target_info parsed: %s", result)
            return result
        except JSONDecodeError as exc:
            logger.error("Gemini JSON decode failed: %s", exc)
            return GeminiService._infer_target_info(query)

    @staticmethod
    def generate_target_summary(target_name: str, uniprot_data: Dict[str, Any]) -> str:
        prompt = (
            f"You are a drug discovery scientist preparing a target-specific briefing for {target_name}. "
            "Write exactly three compact paragraphs covering: biological function, disease linkage, and why this "
            "specific target is druggable or difficult. Reference only the supplied target evidence, avoid generic "
            "drug-discovery filler, and mention concrete identifiers or structure evidence when available. "
            f"Evidence: {uniprot_data}. Plain text only, no markdown."
        )
        fallback = (
            f"{target_name} fallback summary: this target has relevant biology, disease context, and "
            "enough scientific rationale to remain interesting for drug discovery review."
        )

        raw_text = GeminiService._post_prompt(prompt)
        if not raw_text:
            return fallback

        logger.info("generate_target_summary text: %s", raw_text)
        return raw_text.strip() or fallback

    @staticmethod
    def generate_molecule_rationale(smiles: str, admet_scores: Dict[str, Any], docking_score: float) -> str:
        prompt = (
            f"Explain in 2 sentences how this exact molecule (SMILES: {smiles}) balances potency and developability. "
            "Use the supplied ADMET and docking values directly, mention at least one concrete strength and one concrete risk, "
            "and avoid generic praise. "
            f"ADMET: {admet_scores}. Docking score: {docking_score} kcal/mol."
        )
        fallback = (
            f"This molecule remains a plausible candidate because its ADMET profile is usable for triage and "
            f"its docking score of {docking_score} kcal/mol suggests it may warrant follow-up."
        )

        raw_text = GeminiService._post_prompt(prompt)
        if not raw_text:
            return fallback

        logger.info("generate_molecule_rationale text: %s", raw_text)
        return raw_text.strip() or fallback
