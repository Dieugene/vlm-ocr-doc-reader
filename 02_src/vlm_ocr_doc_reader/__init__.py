"""
VLM OCR Document Reader - Universal module for document processing via Vision Language Models.

Public API:
- DocumentReader: primary entry point with Resolution Levels (scan/resolve/verify)
- FullDescriptionOperation: legacy monolithic three-pass operation
"""

__version__ = "0.1.0"

# Core classes
from .core.reader import DocumentReader
from .core.processor import DocumentProcessor
from .core.vlm_client import BaseVLMClient
from .core.qwen_vlm_client import QwenVLMClient
from .core.vlm_agent import VLMAgent
from .core.ocr_client import BaseOCRClient, QwenOCRClient, OCRConfig
from .core.ocr_tool import OCRTool

# Operations
from .operations.base import BaseOperation
from .operations.full_description import FullDescriptionOperation

# Schemas - Config
from .schemas.config import ProcessorConfig, VLMConfig, OCRConfig
from .schemas.document import DocumentData, HeaderInfo, TableInfo
from .schemas.common import PageInfo, ClusterInfo, TriageResult
from .preprocessing.renderer import RenderConfig

# Resolution Levels types (ADR-001)
from .core.state import PageResolution, OCRRegistryEntry, open_document

__all__ = [
    # Version
    "__version__",

    # Core classes
    "DocumentReader",
    "DocumentProcessor",
    "BaseVLMClient",
    "QwenVLMClient",
    "VLMAgent",
    "BaseOCRClient",
    "QwenOCRClient",
    "OCRTool",

    # Operations
    "BaseOperation",
    "FullDescriptionOperation",

    # Schemas - Config
    "ProcessorConfig",
    "VLMConfig",
    "OCRConfig",
    "RenderConfig",

    # Schemas - Document
    "DocumentData",
    "HeaderInfo",
    "TableInfo",

    # Schemas - Common
    "PageInfo",
    "ClusterInfo",
    "TriageResult",

    # Resolution Levels (ADR-001)
    "PageResolution",
    "OCRRegistryEntry",
    "open_document",
]
