"""
VLM OCR Document Reader - Universal module for document processing via Vision Language Models.

This package provides high-level operations for document analysis:
- DocumentReader: Public API for document lifecycle (ADR-001 Resolution Levels)
- FullDescriptionOperation: Extract text and structure (contract with project 07)
- ClusteringOperation: Group pages by semantic similarity
- TriageOperation: Find pages matching criteria
"""

__version__ = "0.1.0"

# Core classes
from .core.reader import DocumentReader
from .core.processor import DocumentProcessor
from .core.vlm_client import BaseVLMClient, GeminiVLMClient
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
    "GeminiVLMClient",
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
