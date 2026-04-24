"""Compatibility wrapper around the centralized Gemini service."""

import logging
from typing import Any, Dict

from app.services.gemini_service import GeminiService

logger = logging.getLogger(__name__)


class GeminiExtractor:
    """Backward-compatible target extraction wrapper."""

    def __init__(self, api_key: str = None):
        self.api_key = api_key

    def extract_target_info(self, query: str) -> Dict[str, Any]:
        result = GeminiService.extract_target_info(query)
        logger.info("GeminiExtractor delegated result: %s", result)
        return result


def get_gemini_extractor() -> GeminiExtractor:
    """Get or create Gemini extractor instance."""
    return GeminiExtractor()
