"""DocumentProcessor - Main class for document processing."""

import logging
import os
from pathlib import Path
from typing import List, Union, Optional

from dotenv import load_dotenv

from ..schemas.common import PageInfo
from ..schemas.config import ProcessorConfig, VLMConfig
from ..preprocessing.renderer import PDFRenderer, RenderConfig
from .vlm_client import BaseVLMClient, GeminiVLMClient
from .state import StateManager, MemoryStorage, DiskStorage
from .vlm_agent import VLMAgent
from .ocr_client import BaseOCRClient, QwenOCRClient, OCRConfig
from .ocr_tool import OCRTool

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """Main class for document processing.

    Supports:
    - PDF files with automatic rendering
    - PNG arrays (pre-rendered images)

    Features:
    - Page access via properties
    - State management (memory or disk)
    - VLM client integration
    """

    def __init__(
        self,
        source: Union[Path, List[bytes]],
        vlm_agent: Optional[VLMAgent] = None,
        state_manager: Optional[StateManager] = None,
        auto_save: bool = True,
        config: Optional[ProcessorConfig] = None,
    ):
        """Initialize document processor.

        Args:
            source: PDF file path or list of PNG bytes
            vlm_agent: VLM agent (optional, created from config if not provided)
            state_manager: State manager instance (optional, created if not provided)
            auto_save: Automatically save state after operations
            config: Processor configuration
        """
        # Initialize config
        self.config = config or ProcessorConfig()
        self.auto_save = auto_save

        # 1. Initialize state manager FIRST (needed by OCR tool)
        if state_manager is None:
            if self.config.state_dir is not None:
                storage = DiskStorage(self.config.state_dir)
            else:
                storage = MemoryStorage()
            state_manager = StateManager(storage)
            logger.info(
                f"Created StateManager with {type(storage).__name__} "
                f"(state_dir={self.config.state_dir})"
            )

        self.state_manager = state_manager

        # 2. Initialize VLM Agent if not provided
        if vlm_agent is None:
            # Need API key from environment
            load_dotenv()
            api_key = os.getenv("GEMINI_API_KEY")

            if not api_key:
                raise ValueError(
                    "GEMINI_API_KEY not found in environment. "
                    "Please set it in .env file or pass vlm_agent explicitly."
                )

            # Create VLM client
            vlm_config = VLMConfig(api_key=api_key)
            vlm_client = GeminiVLMClient(vlm_config)

            # Create OCR client and tool (optional, if QWEN_API_KEY is set)
            try:
                ocr_config = OCRConfig()  # Loads QWEN_API_KEY from environment
                ocr_client = QwenOCRClient(ocr_config)
                ocr_tool = OCRTool(ocr_client, self.state_manager)
                logger.info("Created QwenOCRClient from environment")
            except ValueError:
                # QWEN_API_KEY not set - OCR tool will not be available
                ocr_tool = None
                logger.warning(
                    "QWEN_API_KEY not found - OCR tool will not be registered. "
                    "VLM will still work but cannot call OCR."
                )

            # Create VLM agent and register OCR tool if available
            vlm_agent = VLMAgent(vlm_client)

            if ocr_tool:
                vlm_agent.register_tool(ocr_tool.to_tool_definition(), ocr_tool.execute)
                logger.info("Created VLM Agent with OCR Tool registered")
            else:
                logger.info("Created VLM Agent without OCR Tool")

        self.vlm_agent = vlm_agent

        # Initialize pages based on source type
        self._pages: List[PageInfo] = []

        if isinstance(source, Path):
            # PDF file - render pages
            logger.info(f"Initializing from PDF: {source}")
            self._init_from_pdf(source)

        elif isinstance(source, list):
            # PNG array - use as is
            logger.info(f"Initializing from PNG array ({len(source)} images)")
            self._init_from_png_array(source)

        else:
            raise TypeError(
                f"Invalid source type: {type(source)}. "
                "Expected Path or List[bytes]"
            )

        logger.info(f"DocumentProcessor initialized with {len(self._pages)} pages")

    def _init_from_pdf(self, pdf_path: Path) -> None:
        """Initialize from PDF file by rendering pages.

        Args:
            pdf_path: Path to PDF file
        """
        # Create renderer with config DPI
        render_config = RenderConfig(dpi=self.config.render_dpi)
        renderer = PDFRenderer(render_config)

        # Render all pages
        rendered = renderer.render_pdf(pdf_path)

        # Create PageInfo objects (1-based page numbers)
        self._pages = [
            PageInfo(index=page_num, image=img_bytes)
            for page_num, img_bytes in rendered
        ]

        # Save pages to state if auto_save enabled
        if self.auto_save:
            for page_info in self._pages:
                self.state_manager.save_page(page_info.index, page_info.image)

    def _init_from_png_array(self, png_array: List[bytes]) -> None:
        """Initialize from array of PNG bytes.

        Args:
            png_array: List of PNG image bytes
        """
        # Create PageInfo objects (1-based page numbers)
        self._pages = [
            PageInfo(index=i + 1, image=img_bytes)
            for i, img_bytes in enumerate(png_array)
        ]

        # Save pages to state if auto_save enabled
        if self.auto_save:
            for page_info in self._pages:
                self.state_manager.save_page(page_info.index, page_info.image)

    @property
    def pages(self) -> List[PageInfo]:
        """Get list of all document pages.

        Returns:
            List of PageInfo objects (1-based page numbers)
        """
        return self._pages

    @property
    def num_pages(self) -> int:
        """Get number of pages in document.

        Returns:
            Number of pages
        """
        return len(self._pages)

    def save_state(self) -> None:
        """Explicitly save state.

        For MemoryStorage this ensures in-memory state is current.
        For DiskStorage this is a no-op (data already saved).
        """
        self.state_manager.save_state()
        logger.info("State saved explicitly")

    def load_state(self) -> None:
        """Load state from storage.

        For MemoryStorage this is a no-op.
        For DiskStorage this loads all available data.
        """
        self.state_manager.load_state()
        logger.info("State loaded from storage")
