"""Unit tests for DocumentProcessor."""

from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest

from vlm_ocr_doc_reader.core.processor import DocumentProcessor
from vlm_ocr_doc_reader.core.state import MemoryStorage, StateManager
from vlm_ocr_doc_reader.core.vlm_client import GeminiVLMClient
from vlm_ocr_doc_reader.schemas.config import VLMConfig


@pytest.fixture
def mock_images():
    """Create mock PNG images."""
    # Create minimal valid PNG bytes (1x1 pixel)
    png_header = b"\x89PNG\r\n\x1a\n"
    ihdr = b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    idat = b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\x0d\n-\xb4"
    iend = b"\x00\x00\x00\x00IEND\xaeB`\x82"
    return png_header + ihdr + idat + iend


@pytest.fixture
def mock_vlm_client():
    """Create mock VLM client."""
    client = Mock(spec=GeminiVLMClient)
    client.invoke.return_value = {
        "text": {"response": "ok"},
        "raw": {}
    }
    return client


@pytest.fixture
def mock_state_manager():
    """Create mock state manager."""
    storage = MemoryStorage()
    return StateManager(storage)


class TestDocumentProcessorInit:
    """Test DocumentProcessor initialization."""

    def test_init_from_png_array(self, mock_vlm_client, mock_state_manager, mock_images):
        """Test initialization from PNG array."""
        png_array = [mock_images, mock_images, mock_images]

        processor = DocumentProcessor(
            source=png_array,
            vlm_client=mock_vlm_client,
            state_manager=mock_state_manager,
            auto_save=True
        )

        assert processor.num_pages == 3
        assert len(processor.pages) == 3

        # Check page numbers are 1-based
        for i, page in enumerate(processor.pages):
            assert page.index == i + 1
            assert page.image == mock_images

    @patch('vlm_ocr_doc_reader.core.processor.os.getenv')
    @patch('vlm_ocr_doc_reader.core.processor.load_dotenv')
    def test_init_from_pdf_renders_pages(
        self, mock_load_dotenv, mock_getenv, mock_vlm_client, mock_state_manager
    ):
        """Test initialization from PDF renders pages."""
        # Mock environment variable
        mock_getenv.return_value = "test_api_key"

        # Create mock PDF path
        pdf_path = Path("/tmp/test.pdf")

        # Mock PDFRenderer
        mock_rendered = [
            (1, b"png1"),
            (2, b"png2"),
            (3, b"png3")
        ]

        with patch('vlm_ocr_doc_reader.core.processor.PDFRenderer') as MockRenderer:
            mock_renderer_instance = Mock()
            mock_renderer_instance.render_pdf.return_value = mock_rendered
            MockRenderer.return_value = mock_renderer_instance

            processor = DocumentProcessor(
                source=pdf_path,
                vlm_client=mock_vlm_client,
                state_manager=mock_state_manager,
                auto_save=True
            )

            # Should have rendered PDF
            mock_renderer_instance.render_pdf.assert_called_once_with(pdf_path)

            # Should have 3 pages
            assert processor.num_pages == 3
            assert len(processor.pages) == 3

            # Check page numbers
            for i, page in enumerate(processor.pages):
                assert page.index == i + 1

    def test_init_invalid_source_type(self, mock_vlm_client, mock_state_manager):
        """Test that invalid source type raises TypeError."""
        with pytest.raises(TypeError) as exc_info:
            DocumentProcessor(
                source="invalid_string",  # Should be Path or List[bytes]
                vlm_client=mock_vlm_client,
                state_manager=mock_state_manager
            )

        assert "Invalid source type" in str(exc_info.value)

    @patch('vlm_ocr_doc_reader.core.processor.os.getenv')
    @patch('vlm_ocr_doc_reader.core.processor.load_dotenv')
    def test_init_creates_vlm_client_from_env(
        self, mock_load_dotenv, mock_getenv, mock_state_manager, mock_images
    ):
        """Test that VLM client is created from environment if not provided."""
        # Mock environment variable
        mock_getenv.return_value = "env_api_key"

        with patch('vlm_ocr_doc_reader.core.processor.GeminiVLMClient') as MockClient:
            mock_client_instance = Mock()
            mock_client_instance.invoke.return_value = {"text": {}, "raw": {}}
            MockClient.return_value = mock_client_instance

            processor = DocumentProcessor(
                source=[mock_images],
                state_manager=mock_state_manager
            )

            # Should have created VLM client
            MockClient.assert_called_once()
            call_args = MockClient.call_args[0][0]
            assert call_args.api_key == "env_api_key"

    @patch('vlm_ocr_doc_reader.core.processor.os.getenv')
    @patch('vlm_ocr_doc_reader.core.processor.load_dotenv')
    def test_init_raises_error_without_api_key(
        self, mock_load_dotenv, mock_getenv, mock_state_manager, mock_images
    ):
        """Test that missing API key raises ValueError."""
        # Mock missing API key
        mock_getenv.return_value = None

        with pytest.raises(ValueError) as exc_info:
            DocumentProcessor(
                source=[mock_images],
                state_manager=mock_state_manager
            )

        assert "GEMINI_API_KEY not found" in str(exc_info.value)

    def test_init_creates_memory_storage_by_default(
        self, mock_vlm_client, mock_images
    ):
        """Test that MemoryStorage is created by default."""
        processor = DocumentProcessor(
            source=[mock_images],
            vlm_client=mock_vlm_client,
            auto_save=False
        )

        # Check that state manager was created
        assert processor.state_manager is not None
        assert isinstance(processor.state_manager.storage, MemoryStorage)


class TestDocumentProcessorProperties:
    """Test DocumentProcessor properties."""

    def test_pages_property(self, mock_vlm_client, mock_state_manager, mock_images):
        """Test pages property returns list of PageInfo."""
        png_array = [mock_images, mock_images]

        processor = DocumentProcessor(
            source=png_array,
            vlm_client=mock_vlm_client,
            state_manager=mock_state_manager,
            auto_save=False
        )

        pages = processor.pages
        assert len(pages) == 2
        assert all(hasattr(page, 'index') for page in pages)
        assert all(hasattr(page, 'image') for page in pages)

    def test_num_pages_property(self, mock_vlm_client, mock_state_manager, mock_images):
        """Test num_pages property."""
        png_array = [mock_images] * 5

        processor = DocumentProcessor(
            source=png_array,
            vlm_client=mock_vlm_client,
            state_manager=mock_state_manager,
            auto_save=False
        )

        assert processor.num_pages == 5


class TestDocumentProcessorStateManagement:
    """Test state management."""

    def test_auto_save_saves_pages(self, mock_vlm_client, mock_images):
        """Test that auto_save=True saves pages to state."""
        storage = MemoryStorage()
        state_manager = StateManager(storage)

        png_array = [mock_images, mock_images]

        processor = DocumentProcessor(
            source=png_array,
            vlm_client=mock_vlm_client,
            state_manager=state_manager,
            auto_save=True
        )

        # Check that pages were saved
        assert storage.exists("pages/001")
        assert storage.exists("pages/002")

        # Load and verify
        page1 = storage.load("pages/001")
        page2 = storage.load("pages/002")
        assert page1 == mock_images
        assert page2 == mock_images

    def test_no_auto_save_skips_saving(self, mock_vlm_client, mock_images):
        """Test that auto_save=False does not save pages."""
        storage = MemoryStorage()
        state_manager = StateManager(storage)

        png_array = [mock_images]

        processor = DocumentProcessor(
            source=png_array,
            vlm_client=mock_vlm_client,
            state_manager=state_manager,
            auto_save=False
        )

        # Pages should not be saved
        assert not storage.exists("pages/001")

    def test_save_state_explicit(self, mock_vlm_client, mock_state_manager, mock_images):
        """Test explicit save_state call."""
        processor = DocumentProcessor(
            source=[mock_images],
            vlm_client=mock_vlm_client,
            state_manager=mock_state_manager,
            auto_save=False
        )

        # Call save_state
        processor.save_state()

        # StateManager save_state should be called
        # (In current implementation this is a no-op for MemoryStorage)
        # Just verify method exists and is callable
        assert hasattr(processor, 'save_state')
        assert callable(processor.save_state)

    def test_load_state_explicit(self, mock_vlm_client, mock_state_manager, mock_images):
        """Test explicit load_state call."""
        processor = DocumentProcessor(
            source=[mock_images],
            vlm_client=mock_vlm_client,
            state_manager=mock_state_manager,
            auto_save=False
        )

        # Call load_state
        processor.load_state()

        # StateManager load_state should be called
        assert hasattr(processor, 'load_state')
        assert callable(processor.load_state)
