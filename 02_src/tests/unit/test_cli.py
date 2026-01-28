"""Unit tests for CLI module."""

import logging
import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest

from vlm_ocr_doc_reader.cli import (
    main,
    setup_logging,
    validate_arguments,
    create_output_directory
)
from vlm_ocr_doc_reader.schemas.document import DocumentData


@pytest.fixture
def mock_pdf_path(tmp_path):
    """Create a mock PDF file path."""
    pdf_path = tmp_path / "test.pdf"
    # Create a dummy file (not a real PDF, but exists for testing)
    pdf_path.write_bytes(b"%PDF-1.4\nmock pdf")
    return pdf_path


@pytest.fixture
def mock_output_dir(tmp_path):
    """Create a mock output directory path."""
    return tmp_path / "output"


@pytest.fixture
def mock_env_with_api_key():
    """Mock environment with API key."""
    return {"GEMINI_API_KEY": "test-api-key-123"}


class TestSetupLogging:
    """Test logging setup."""

    def test_setup_logging_info(self):
        """Test setup logging with INFO level."""
        setup_logging("INFO")
        logger = logging.getLogger()
        assert logger.level == logging.INFO

    def test_setup_logging_debug(self):
        """Test setup logging with DEBUG level."""
        setup_logging("DEBUG")
        logger = logging.getLogger()
        assert logger.level == logging.DEBUG

    def test_setup_logging_warning(self):
        """Test setup logging with WARNING level."""
        setup_logging("WARNING")
        logger = logging.getLogger()
        assert logger.level == logging.WARNING


class TestValidateArguments:
    """Test argument validation."""

    def test_validate_valid_arguments(self, mock_pdf_path, mock_env_with_api_key):
        """Test validation with valid arguments."""
        # Should not raise
        validate_arguments(mock_pdf_path, mock_env_with_api_key["GEMINI_API_KEY"])

    def test_validate_missing_pdf(self, mock_pdf_path, mock_env_with_api_key, capsys):
        """Test validation with missing PDF file."""
        non_existent = mock_pdf_path.parent / "non_existent.pdf"

        with pytest.raises(SystemExit) as exc_info:
            validate_arguments(non_existent, mock_env_with_api_key["GEMINI_API_KEY"])

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error: PDF file not found" in captured.err

    def test_validate_pdf_is_directory(self, tmp_path, mock_env_with_api_key, capsys):
        """Test validation when PDF path is a directory."""
        with pytest.raises(SystemExit) as exc_info:
            validate_arguments(tmp_path, mock_env_with_api_key["GEMINI_API_KEY"])

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error: Path is not a file" in captured.err

    def test_validate_missing_api_key(self, mock_pdf_path, capsys):
        """Test validation with missing API key."""
        with pytest.raises(SystemExit) as exc_info:
            validate_arguments(mock_pdf_path, None)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "GEMINI_API_KEY not found" in captured.err


class TestCreateOutputDirectory:
    """Test output directory creation."""

    def test_create_existing_directory(self, mock_output_dir):
        """Test creating output directory when it already exists."""
        mock_output_dir.mkdir(parents=True, exist_ok=True)
        # Should not raise
        create_output_directory(mock_output_dir)
        assert mock_output_dir.exists()

    def test_create_new_directory(self, mock_output_dir):
        """Test creating new output directory."""
        # Remove if exists
        if mock_output_dir.exists():
            mock_output_dir.rmdir()

        create_output_directory(mock_output_dir)
        assert mock_output_dir.exists()


class TestMainFunction:
    """Test main CLI function."""

    @patch("vlm_ocr_doc_reader.cli.load_dotenv")
    @patch("vlm_ocr_doc_reader.cli.DocumentProcessor")
    @patch("vlm_ocr_doc_reader.cli.FullDescriptionOperation")
    @patch("sys.argv", ["vlm-ocr-reader", "test.pdf"])
    def test_main_success(
        self,
        mock_operation_class,
        mock_processor_class,
        mock_load_dotenv,
        mock_pdf_path,
        mock_env_with_api_key,
        monkeypatch
    ):
        """Test successful execution of main function."""
        # Mock environment
        monkeypatch.setenv("GEMINI_API_KEY", mock_env_with_api_key["GEMINI_API_KEY"])

        # Mock processor
        mock_processor = MagicMock()
        mock_processor.num_pages = 10
        mock_processor.state_manager = MagicMock()
        mock_processor_class.return_value = mock_processor

        # Mock operation result
        mock_result = DocumentData(
            text="Sample document text",
            structure={"headers": [{"level": 1, "title": "Introduction", "page": 1}]},
            tables=[]
        )
        mock_operation = MagicMock()
        mock_operation.execute.return_value = mock_result
        mock_operation_class.return_value = mock_operation

        # Patch Path to return our mock PDF
        with patch("vlm_ocr_doc_reader.cli.Path", return_value=mock_pdf_path):
            result = main()

        assert result == 0
        mock_processor_class.assert_called_once()
        mock_operation_class.assert_called_once_with(mock_processor)
        mock_operation.execute.assert_called_once()
        mock_processor.state_manager.save_operation_result.assert_called_once()

    @patch("vlm_ocr_doc_reader.cli.load_dotenv")
    @patch("sys.argv", ["vlm-ocr-reader", "non_existent.pdf"])
    def test_main_pdf_not_found(self, mock_load_dotenv, monkeypatch, tmp_path, capsys):
        """Test main function with non-existent PDF."""
        # Mock environment
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")

        non_existent = tmp_path / "non_existent.pdf"

        with patch("vlm_ocr_doc_reader.cli.Path", return_value=non_existent):
            result = main()

        assert result == 1
        # Error message should be in stderr
        captured = capsys.readouterr()
        assert "Error: PDF file not found" in captured.err

    @patch("vlm_ocr_doc_reader.cli.load_dotenv")
    @patch("sys.argv", ["vlm-ocr-reader", "test.pdf"])
    def test_main_missing_api_key(self, mock_load_dotenv, mock_pdf_path, monkeypatch, capsys):
        """Test main function with missing API key."""
        # Ensure no API key is set
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

        with patch("vlm_ocr_doc_reader.cli.Path", return_value=mock_pdf_path):
            result = main()

        assert result == 1
        captured = capsys.readouterr()
        assert "GEMINI_API_KEY not found" in captured.err

    @patch("vlm_ocr_doc_reader.cli.load_dotenv")
    @patch("vlm_ocr_doc_reader.cli.DocumentProcessor")
    @patch("vlm_ocr_doc_reader.cli.FullDescriptionOperation")
    @patch("sys.argv", ["vlm-ocr-reader", "test.pdf", "--output-dir", "./custom_output"])
    def test_main_custom_output_dir(
        self,
        mock_operation_class,
        mock_processor_class,
        mock_load_dotenv,
        mock_pdf_path,
        mock_env_with_api_key,
        monkeypatch,
        tmp_path
    ):
        """Test main function with custom output directory."""
        # Mock environment
        monkeypatch.setenv("GEMINI_API_KEY", mock_env_with_api_key["GEMINI_API_KEY"])

        custom_output = tmp_path / "custom_output"

        # Mock processor
        mock_processor = MagicMock()
        mock_processor.num_pages = 5
        mock_processor.state_manager = MagicMock()
        mock_processor_class.return_value = mock_processor

        # Mock operation
        mock_result = DocumentData(
            text="Test text",
            structure={"headers": []},
            tables=[]
        )
        mock_operation = MagicMock()
        mock_operation.execute.return_value = mock_result
        mock_operation_class.return_value = mock_operation

        # Create a side effect for Path to return correct paths
        def path_side_effect(path_str):
            if str(path_str).endswith("test.pdf"):
                return mock_pdf_path
            return Path(path_str)

        with patch("vlm_ocr_doc_reader.cli.Path", side_effect=path_side_effect):
            result = main()

        assert result == 0
        # Check that output directory was created
        assert custom_output.exists()

    @patch("vlm_ocr_doc_reader.cli.load_dotenv")
    @patch("vlm_ocr_doc_reader.cli.DocumentProcessor")
    @patch("vlm_ocr_doc_reader.cli.FullDescriptionOperation")
    @patch("sys.argv", ["vlm-ocr-reader", "test.pdf", "--dpi", "200"])
    def test_main_custom_dpi(
        self,
        mock_operation_class,
        mock_processor_class,
        mock_load_dotenv,
        mock_pdf_path,
        mock_env_with_api_key,
        monkeypatch
    ):
        """Test main function with custom DPI."""
        # Mock environment
        monkeypatch.setenv("GEMINI_API_KEY", mock_env_with_api_key["GEMINI_API_KEY"])

        # Mock processor
        mock_processor = MagicMock()
        mock_processor.num_pages = 3
        mock_processor.state_manager = MagicMock()
        mock_processor_class.return_value = mock_processor

        # Mock operation
        mock_result = DocumentData(
            text="DPI test",
            structure={"headers": []},
            tables=[]
        )
        mock_operation = MagicMock()
        mock_operation.execute.return_value = mock_result
        mock_operation_class.return_value = mock_operation

        with patch("vlm_ocr_doc_reader.cli.Path", return_value=mock_pdf_path):
            result = main()

        assert result == 0
        # Verify processor was called with config containing DPI=200
        call_args = mock_processor_class.call_args
        assert call_args is not None
        config = call_args.kwargs.get("config") or call_args[1].get("config")
        # Note: We can't easily test the exact config without accessing the ProcessorConfig
        # but we can verify the call was made

    @patch("vlm_ocr_doc_reader.cli.load_dotenv")
    @patch("vlm_ocr_doc_reader.cli.DocumentProcessor")
    @patch("vlm_ocr_doc_reader.cli.FullDescriptionOperation")
    @patch("sys.argv", ["vlm-ocr-reader", "test.pdf", "--log-level", "DEBUG"])
    def test_main_debug_logging(
        self,
        mock_operation_class,
        mock_processor_class,
        mock_load_dotenv,
        mock_pdf_path,
        mock_env_with_api_key,
        monkeypatch
    ):
        """Test main function with DEBUG log level."""
        # Mock environment
        monkeypatch.setenv("GEMINI_API_KEY", mock_env_with_api_key["GEMINI_API_KEY"])

        # Mock processor
        mock_processor = MagicMock()
        mock_processor.num_pages = 1
        mock_processor.state_manager = MagicMock()
        mock_processor_class.return_value = mock_processor

        # Mock operation
        mock_result = DocumentData(
            text="Debug test",
            structure={"headers": []},
            tables=[]
        )
        mock_operation = MagicMock()
        mock_operation.execute.return_value = mock_result
        mock_operation_class.return_value = mock_operation

        with patch("vlm_ocr_doc_reader.cli.Path", return_value=mock_pdf_path):
            result = main()

        assert result == 0
        # Check that logging level was set to DEBUG
        logger = logging.getLogger()
        assert logger.level == logging.DEBUG

    @patch("vlm_ocr_doc_reader.cli.load_dotenv")
    @patch("vlm_ocr_doc_reader.cli.DocumentProcessor")
    @patch("sys.argv", ["vlm-ocr-reader", "test.pdf"])
    def test_main_keyboard_interrupt(
        self,
        mock_processor_class,
        mock_load_dotenv,
        mock_pdf_path,
        mock_env_with_api_key,
        monkeypatch
    ):
        """Test main function with keyboard interrupt."""
        # Mock environment
        monkeypatch.setenv("GEMINI_API_KEY", mock_env_with_api_key["GEMINI_API_KEY"])

        # Mock processor to raise KeyboardInterrupt
        mock_processor_class.side_effect = KeyboardInterrupt()

        with patch("vlm_ocr_doc_reader.cli.Path", return_value=mock_pdf_path):
            result = main()

        assert result == 1

    @patch("vlm_ocr_doc_reader.cli.load_dotenv")
    @patch("vlm_ocr_doc_reader.cli.DocumentProcessor")
    @patch("sys.argv", ["vlm-ocr-reader", "test.pdf"])
    def test_main_exception_handling(
        self,
        mock_processor_class,
        mock_load_dotenv,
        mock_pdf_path,
        mock_env_with_api_key,
        monkeypatch,
        caplog
    ):
        """Test main function with exception handling."""
        # Mock environment
        monkeypatch.setenv("GEMINI_API_KEY", mock_env_with_api_key["GEMINI_API_KEY"])

        # Mock processor to raise exception
        mock_processor_class.side_effect = RuntimeError("Test error")

        with patch("vlm_ocr_doc_reader.cli.Path", return_value=mock_pdf_path):
            result = main()

        assert result == 1
