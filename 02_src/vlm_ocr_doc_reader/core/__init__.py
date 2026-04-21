"""Core components: state management, processor, agents, and clients."""

from .state import (
    StorageBackend,
    MemoryStorage,
    DiskStorage,
    DocumentState,
    StateManager,
    # Resolution Levels (ADR-001)
    ResolutionLevel,
    PageResolution,
    OCRRegistryEntry,
    VerifyResult,
    DocumentMetadata,
    ResolutionDocumentState,
    # Workspace (ADR-001)
    WorkspacePaths,
    WorkspaceStorage,
    compute_content_hash,
    build_document_subdir_name,
    open_document,
)
from .ocr_client import (
    BaseOCRClient,
    OCRConfig,
    QwenClientError,
    QwenOCRClient,
)
from .ocr_tool import OCRTool
from .vlm_client import BaseVLMClient
from .qwen_vlm_client import QwenVLMClient
from .vlm_agent import VLMAgent
from .processor import DocumentProcessor
from .reader import DocumentReader

__all__ = [
    # State management
    "StorageBackend",
    "MemoryStorage",
    "DiskStorage",
    "DocumentState",
    "StateManager",
    # Resolution Levels (ADR-001)
    "ResolutionLevel",
    "PageResolution",
    "OCRRegistryEntry",
    "VerifyResult",
    "DocumentMetadata",
    "ResolutionDocumentState",
    # Workspace (ADR-001)
    "WorkspacePaths",
    "WorkspaceStorage",
    "compute_content_hash",
    "build_document_subdir_name",
    "open_document",
    # OCR
    "BaseOCRClient",
    "OCRConfig",
    "QwenClientError",
    "QwenOCRClient",
    "OCRTool",
    # VLM
    "BaseVLMClient",
    "QwenVLMClient",
    "VLMAgent",
    "DocumentProcessor",
    "DocumentReader",
]
