"""
Unit tests for centralized Gemini service.
"""

import sys
from pathlib import Path
import requests
from unittest.mock import MagicMock, patch

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.gemini_service import GeminiService


class TestGeminiService:
    @patch("app.services.gemini_service.settings")
    @patch("app.services.gemini_service.requests.post")
    def test_extract_target_info_success(self, mock_post, mock_settings):
        GeminiService._response_cache.clear()
        mock_settings.GEMINI_API_KEY = "test-key"
        mock_settings.GEMINI_MODEL = "gemini-2.5-flash"
        mock_settings.GEMINI_MAX_RETRIES = 0
        mock_settings.GEMINI_RETRY_BASE_SECONDS = 0
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": '{"protein_name":"Beta-secretase 1","gene_symbol":"BACE1","disease":"Alzheimer disease","indication":"Alzheimer disease"}'
                            }
                        ]
                    }
                }
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        result = GeminiService.extract_target_info("BACE1 protease in Alzheimer's disease")

        assert result["protein_name"] == "Beta-secretase 1"
        assert result["gene_symbol"] == "BACE1"
        assert result["disease"] == "Alzheimer disease"

    @patch("app.services.gemini_service.settings")
    @patch("app.services.gemini_service.requests.post")
    def test_generate_target_summary_success(self, mock_post, mock_settings):
        GeminiService._response_cache.clear()
        mock_settings.GEMINI_API_KEY = "test-key"
        mock_settings.GEMINI_MODEL = "gemini-2.5-flash"
        mock_settings.GEMINI_MAX_RETRIES = 0
        mock_settings.GEMINI_RETRY_BASE_SECONDS = 0
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": "BACE1 is an aspartyl protease with disease relevance and a tractable rationale for drug discovery."
                            }
                        ]
                    }
                }
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        result = GeminiService.generate_target_summary("BACE1", {"function": "protease"})

        assert "BACE1" in result

    @patch("app.services.gemini_service.settings")
    @patch("app.services.gemini_service.requests.post")
    def test_generate_molecule_rationale_success(self, mock_post, mock_settings):
        GeminiService._response_cache.clear()
        mock_settings.GEMINI_API_KEY = "test-key"
        mock_settings.GEMINI_MODEL = "gemini-2.5-flash"
        mock_settings.GEMINI_MAX_RETRIES = 0
        mock_settings.GEMINI_RETRY_BASE_SECONDS = 0
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": "This molecule combines favorable ADMET indicators with promising docking behavior. It looks like a sensible candidate for further testing."
                            }
                        ]
                    }
                }
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        result = GeminiService.generate_molecule_rationale("CCO", {"bbbp_traffic": "green"}, -8.2)

        assert "candidate" in result.lower()

    @patch("app.services.gemini_service.settings")
    @patch("app.services.gemini_service.requests.post")
    def test_extract_target_info_json_fallback(self, mock_post, mock_settings):
        GeminiService._response_cache.clear()
        mock_settings.GEMINI_API_KEY = "test-key"
        mock_settings.GEMINI_MODEL = "gemini-2.5-flash"
        mock_settings.GEMINI_MAX_RETRIES = 0
        mock_settings.GEMINI_RETRY_BASE_SECONDS = 0
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "not-json"}]}}]
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        result = GeminiService.extract_target_info("invalid")

        assert result == {
            "protein_name": "",
            "gene_symbol": "",
            "disease": "",
            "indication": "",
        }

    @patch("app.services.gemini_service.settings")
    @patch("app.services.gemini_service.requests.post")
    def test_api_error_fallbacks(self, mock_post, mock_settings):
        GeminiService._response_cache.clear()
        mock_settings.GEMINI_API_KEY = "test-key"
        mock_settings.GEMINI_MODEL = "gemini-2.5-flash"
        mock_settings.GEMINI_MAX_RETRIES = 0
        mock_settings.GEMINI_RETRY_BASE_SECONDS = 0
        mock_post.side_effect = RuntimeError("network failure")

        summary = GeminiService.generate_target_summary("HER2", {"function": "receptor"})
        rationale = GeminiService.generate_molecule_rationale("CCO", {}, -7.1)

        assert "fallback" in summary.lower() or "drug discovery" in summary.lower()
        assert "docking score" in rationale.lower()

    @patch("app.services.gemini_service.time.sleep")
    @patch("app.services.gemini_service.settings")
    @patch("app.services.gemini_service.requests.post")
    def test_rate_limit_retry_then_success(self, mock_post, mock_settings, mock_sleep):
        GeminiService._response_cache.clear()
        mock_settings.GEMINI_API_KEY = "test-key"
        mock_settings.GEMINI_MODEL = "gemini-2.5-flash"
        mock_settings.GEMINI_MAX_RETRIES = 2
        mock_settings.GEMINI_RETRY_BASE_SECONDS = 0

        rate_limited = requests.HTTPError("429 too many requests")
        rate_limited.response = MagicMock(status_code=429, headers={"Retry-After": "1"})
        success_response = MagicMock()
        success_response.raise_for_status.return_value = None
        success_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Recovered response"}]}}]
        }
        mock_post.side_effect = [rate_limited, success_response]

        result = GeminiService.generate_target_summary("BACE1", {"function": "protease"})

        assert result == "Recovered response"
        assert mock_post.call_count == 2
        mock_sleep.assert_called_once()

    @patch("app.services.gemini_service.settings")
    @patch("app.services.gemini_service.requests.post")
    def test_prompt_cache_avoids_duplicate_request(self, mock_post, mock_settings):
        GeminiService._response_cache.clear()
        mock_settings.GEMINI_API_KEY = "test-key"
        mock_settings.GEMINI_MODEL = "gemini-2.5-flash"
        mock_settings.GEMINI_MAX_RETRIES = 0
        mock_settings.GEMINI_RETRY_BASE_SECONDS = 0

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Cached text"}]}}]
        }
        mock_post.return_value = mock_response

        first = GeminiService.generate_target_summary("BACE1", {"function": "protease"})
        second = GeminiService.generate_target_summary("BACE1", {"function": "protease"})

        assert first == "Cached text"
        assert second == "Cached text"
        assert mock_post.call_count == 1
