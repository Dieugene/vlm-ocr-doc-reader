"""Configuration schemas for VLM and document processor."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Import OCRConfig from ocr_client module
from ..core.ocr_client import OCRConfig


@dataclass
class VLMConfig:
    """Configuration for VLM client.

    Attributes:
        api_key: API key for Gemini API
        model: Model name (default: gemini-2.5-flash)
        timeout_sec: Request timeout in seconds
        max_retries: Maximum number of retry attempts
        backoff_base: Base for exponential backoff calculation
        min_interval_s: Minimum interval between requests (throttling)
    """
    api_key: str
    model: str = "gemini-2.5-flash"
    timeout_sec: int = 60
    max_retries: int = 3
    backoff_base: float = 1.5
    min_interval_s: float = 0.6


@dataclass
class ProcessorConfig:
    """Configuration for DocumentProcessor.

    Attributes:
        state_dir: Directory for state persistence (optional)
        auto_save: Automatically save state after operations
        render_dpi: DPI for PDF rendering (default: 150)
        log_level: Logging level (default: INFO)
    """
    state_dir: Optional[Path] = None
    auto_save: bool = True
    render_dpi: int = 150
    log_level: str = "INFO"
