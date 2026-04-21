"""Unit tests for CLI v2 module."""

import logging
import pathlib
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from vlm_ocr_doc_reader.cli import (
    main,
    setup_logging,
    validate_arguments,
    parse_pages_arg,
    ensure_utf8_stdio,
)


@pytest.fixture
def mock_pdf_path(tmp_path):
    """Create a mock PDF file path."""
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\nmock pdf")
    return pdf_path


@pytest.fixture
def mock_env_with_api_key():
    """Mock environment with API key."""
    return {"DASHSCOPE_API_KEY": "test-api-key-123"}


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
        validate_arguments(mock_pdf_path, mock_env_with_api_key["DASHSCOPE_API_KEY"])

    def test_validate_missing_pdf(self, mock_pdf_path, mock_env_with_api_key, capsys):
        """Test validation with missing PDF file."""
        non_existent = mock_pdf_path.parent / "non_existent.pdf"

        with pytest.raises(SystemExit) as exc_info:
            validate_arguments(non_existent, mock_env_with_api_key["DASHSCOPE_API_KEY"])

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error: PDF file not found" in captured.err

    def test_validate_pdf_is_directory(self, tmp_path, mock_env_with_api_key, capsys):
        """Test validation when PDF path is a directory."""
        with pytest.raises(SystemExit) as exc_info:
            validate_arguments(tmp_path, mock_env_with_api_key["DASHSCOPE_API_KEY"])

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error: Path is not a file" in captured.err

    def test_validate_missing_api_key(self, mock_pdf_path, capsys):
        """Test validation with missing API key."""
        with pytest.raises(SystemExit) as exc_info:
            validate_arguments(mock_pdf_path, None)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "DASHSCOPE_API_KEY" in captured.err
        assert "not found" in captured.err


class TestParsePagesArg:
    """Test parse_pages_arg."""

    def test_parse_none(self):
        """None returns None."""
        assert parse_pages_arg(None) is None

    def test_parse_empty_string(self):
        """Empty string returns None."""
        assert parse_pages_arg("") is None
        assert parse_pages_arg("   ") is None

    def test_parse_single_page(self):
        """Single page returns [n]."""
        assert parse_pages_arg("3") == [3]

    def test_parse_comma_separated(self):
        """Comma-separated returns sorted list."""
        assert parse_pages_arg("1,2,5-7") == [1, 2, 5, 6, 7]
        assert parse_pages_arg("5,1,3") == [1, 3, 5]

    def test_parse_range(self):
        """Range N-M returns inclusive list."""
        assert parse_pages_arg("5-7") == [5, 6, 7]
        assert parse_pages_arg("1-1") == [1]

    def test_parse_deduplicates(self):
        """Duplicate pages are removed."""
        assert parse_pages_arg("1,1,2,2") == [1, 2]

    def test_parse_invalid_range(self):
        """Invalid range raises ValueError."""
        with pytest.raises(ValueError, match="Invalid page range"):
            parse_pages_arg("1-2-3")
        with pytest.raises(ValueError, match="lo > hi"):
            parse_pages_arg("5-2")

    def test_parse_invalid_number(self):
        """Invalid number raises ValueError."""
        with pytest.raises(ValueError, match="Invalid page number"):
            parse_pages_arg("abc")


class TestEnsureUtf8Stdio:
    """Test ensure_utf8_stdio."""

    def test_ensure_utf8_stdio_no_error(self):
        """ensure_utf8_stdio does not raise."""
        ensure_utf8_stdio()
        # On non-Windows or UTF-8 console, may do nothing
        assert sys.stdout is not None
        assert sys.stderr is not None


class TestMainSubcommands:
    """Test main CLI with subcommands."""

    @patch("vlm_ocr_doc_reader.cli.load_dotenv")
    @patch("vlm_ocr_doc_reader.cli.DocumentReader")
    @patch("sys.argv", ["vlm-ocr-reader", "scan", "test.pdf"])
    def test_main_scan_success(
        self, mock_reader_class, mock_load_dotenv, mock_pdf_path, mock_env_with_api_key, monkeypatch
    ):
        """Test scan subcommand success."""
        monkeypatch.setenv("DASHSCOPE_API_KEY", mock_env_with_api_key["DASHSCOPE_API_KEY"])
        mock_reader = MagicMock()
        mock_reader.page_status.return_value = {1: "scan", 2: "scan"}
        mock_reader_class.open.return_value = mock_reader

        with patch("vlm_ocr_doc_reader.cli.Path", return_value=mock_pdf_path):
            result = main()

        assert result == 0
        mock_reader_class.open.assert_called_once_with(mock_pdf_path, None)
        mock_reader.scan.assert_called_once_with(pages=None)

    @patch("vlm_ocr_doc_reader.cli.load_dotenv")
    @patch("vlm_ocr_doc_reader.cli.DocumentReader")
    @patch("sys.argv", ["vlm-ocr-reader", "resolve", "test.pdf", "--workspace", "./ws", "--pages", "1,3-5"])
    def test_main_resolve_with_pages(
        self, mock_reader_class, mock_load_dotenv, mock_pdf_path, mock_env_with_api_key, monkeypatch, tmp_path
    ):
        """Test resolve subcommand with --pages."""
        monkeypatch.setenv("DASHSCOPE_API_KEY", mock_env_with_api_key["DASHSCOPE_API_KEY"])
        mock_reader = MagicMock()
        mock_reader_class.open.return_value = mock_reader

        ws = tmp_path / "ws"
        ws.mkdir()

        def path_side_effect(arg):
            if str(arg) == "test.pdf":
                return mock_pdf_path
            if str(arg) == "./ws":
                return ws
            return pathlib.Path(arg)

        with patch("vlm_ocr_doc_reader.cli.Path", side_effect=path_side_effect):
            result = main()

        assert result == 0
        mock_reader_class.open.assert_called_once_with(mock_pdf_path, ws)
        mock_reader.resolve.assert_called_once_with(pages=[1, 3, 4, 5])

    @patch("vlm_ocr_doc_reader.cli.load_dotenv")
    @patch("vlm_ocr_doc_reader.cli.DocumentReader")
    @patch("sys.argv", ["vlm-ocr-reader", "full-description", "test.pdf"])
    def test_main_full_description_success(
        self, mock_reader_class, mock_load_dotenv, mock_pdf_path, mock_env_with_api_key, monkeypatch
    ):
        """Test full-description subcommand (scan + resolve)."""
        monkeypatch.setenv("DASHSCOPE_API_KEY", mock_env_with_api_key["DASHSCOPE_API_KEY"])
        mock_reader = MagicMock()
        mock_reader.get_document_data.return_value = MagicMock(
            text="Sample text",
            structure={"headers": []},
            tables=[],
        )
        mock_reader_class.open.return_value = mock_reader

        with patch("vlm_ocr_doc_reader.cli.Path", return_value=mock_pdf_path):
            result = main()

        assert result == 0
        mock_reader.scan.assert_called_once()
        mock_reader.resolve.assert_called_once()
        mock_reader.get_document_data.assert_called_once()

    @patch("vlm_ocr_doc_reader.cli.load_dotenv")
    @patch("vlm_ocr_doc_reader.cli.DocumentReader")
    @patch("sys.argv", ["vlm-ocr-reader", "full-description", "test.pdf"])
    def test_main_full_description_scan_failure(
        self, mock_reader_class, mock_load_dotenv, mock_pdf_path, mock_env_with_api_key, monkeypatch
    ):
        """full-description should fail-fast when scan operation fails."""
        monkeypatch.setenv("DASHSCOPE_API_KEY", mock_env_with_api_key["DASHSCOPE_API_KEY"])
        mock_reader = MagicMock()
        mock_reader.scan.side_effect = RuntimeError("scan timeout")
        mock_reader_class.open.return_value = mock_reader

        with patch("vlm_ocr_doc_reader.cli.Path", return_value=mock_pdf_path):
            result = main()

        assert result == 1
        mock_reader.scan.assert_called_once()
        mock_reader.resolve.assert_not_called()

    @patch("vlm_ocr_doc_reader.cli.load_dotenv")
    @patch("sys.argv", ["vlm-ocr-reader", "scan", "non_existent.pdf"])
    def test_main_pdf_not_found(self, mock_load_dotenv, monkeypatch, tmp_path, capsys):
        """Test main with non-existent PDF."""
        monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
        non_existent = tmp_path / "non_existent.pdf"

        with patch("vlm_ocr_doc_reader.cli.Path", return_value=non_existent):
            result = main()

        assert result == 1
        captured = capsys.readouterr()
        assert "Error: PDF file not found" in captured.err

    @patch("vlm_ocr_doc_reader.cli.load_dotenv")
    @patch("sys.argv", ["vlm-ocr-reader", "scan", "test.pdf"])
    def test_main_missing_api_key(self, mock_load_dotenv, mock_pdf_path, monkeypatch, capsys):
        """Test main with missing API key."""
        monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
        monkeypatch.delenv("QWEN_API_KEY", raising=False)

        with patch("vlm_ocr_doc_reader.cli.Path", return_value=mock_pdf_path):
            result = main()

        assert result == 1
        captured = capsys.readouterr()
        assert "DASHSCOPE_API_KEY" in captured.err
        assert "not found" in captured.err

    @patch("vlm_ocr_doc_reader.cli.load_dotenv")
    @patch("vlm_ocr_doc_reader.cli.DocumentReader")
    @patch("sys.argv", ["vlm-ocr-reader", "scan", "test.pdf"])
    def test_main_keyboard_interrupt(
        self, mock_reader_class, mock_load_dotenv, mock_pdf_path, mock_env_with_api_key, monkeypatch
    ):
        """Test main with keyboard interrupt."""
        monkeypatch.setenv("DASHSCOPE_API_KEY", mock_env_with_api_key["DASHSCOPE_API_KEY"])
        mock_reader_class.open.side_effect = KeyboardInterrupt()

        with patch("vlm_ocr_doc_reader.cli.Path", return_value=mock_pdf_path):
            result = main()

        assert result == 1

    @patch("vlm_ocr_doc_reader.cli.load_dotenv")
    @patch("vlm_ocr_doc_reader.cli.DocumentReader")
    @patch("sys.argv", ["vlm-ocr-reader", "scan", "test.pdf"])
    def test_main_exception_handling(
        self, mock_reader_class, mock_load_dotenv, mock_pdf_path, mock_env_with_api_key, monkeypatch
    ):
        """Test main with exception."""
        monkeypatch.setenv("DASHSCOPE_API_KEY", mock_env_with_api_key["DASHSCOPE_API_KEY"])
        mock_reader_class.open.side_effect = RuntimeError("Test error")

        with patch("vlm_ocr_doc_reader.cli.Path", return_value=mock_pdf_path):
            result = main()

        assert result == 1
