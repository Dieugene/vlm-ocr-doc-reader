"""Tests for State Manager and storage backends."""

import json
from pathlib import Path
from typing import Any, Dict

import pytest
import yaml

from vlm_ocr_doc_reader.core.state import (
    DocumentState,
    DiskStorage,
    MemoryStorage,
    StateManager,
    StorageBackend,
)


class TestMemoryStorage:
    """Test suite for MemoryStorage backend."""

    @pytest.fixture
    def storage(self) -> MemoryStorage:
        """Create MemoryStorage instance."""
        return MemoryStorage()

    def test_save_and_load(self, storage: MemoryStorage) -> None:
        """Test saving and loading values."""
        storage.save("test_key", "test_value")
        assert storage.load("test_key") == "test_value"

    def test_load_default(self, storage: MemoryStorage) -> None:
        """Test loading non-existent key returns default."""
        assert storage.load("nonexistent", default="default") == "default"
        assert storage.load("nonexistent") is None

    def test_exists(self, storage: MemoryStorage) -> None:
        """Test exists method."""
        assert not storage.exists("test_key")
        storage.save("test_key", "value")
        assert storage.exists("test_key")

    def test_save_overwrite(self, storage: MemoryStorage) -> None:
        """Test overwriting existing value."""
        storage.save("key", "value1")
        storage.save("key", "value2")
        assert storage.load("key") == "value2"

    def test_save_different_types(self, storage: MemoryStorage) -> None:
        """Test saving different data types."""
        # String
        storage.save("str_key", "string_value")
        assert storage.load("str_key") == "string_value"

        # Dict
        data = {"key": "value", "number": 123}
        storage.save("dict_key", data)
        assert storage.load("dict_key") == data

        # Bytes
        byte_data = b"binary_data"
        storage.save("bytes_key", byte_data)
        assert storage.load("bytes_key") == byte_data

        # Int
        storage.save("int_key", 42)
        assert storage.load("int_key") == 42


class TestDiskStorage:
    """Test suite for DiskStorage backend."""

    @pytest.fixture
    def storage(self, tmp_path: Path) -> DiskStorage:
        """Create DiskStorage instance with temporary directory."""
        return DiskStorage(tmp_path)

    def test_directory_creation(self, storage: DiskStorage) -> None:
        """Test that all required directories are created."""
        assert storage.cache_dir.exists()
        assert storage.pages_dir.exists()
        assert storage.vlm_responses_dir.exists()
        assert storage.results_dir.exists()
        assert storage.logs_dir.exists()

    def test_save_and_load_page(self, storage: DiskStorage) -> None:
        """Test saving and loading page images."""
        # Save PNG bytes
        page_data = b"\x89PNG\r\n\x1a\n"  # PNG header
        storage.save("pages/001", page_data)

        # Load back
        loaded = storage.load("pages/001")
        assert loaded == page_data

    def test_save_vlm_response(self, storage: DiskStorage) -> None:
        """Test saving VLM response as JSON."""
        response = {
            "operation": "test",
            "result": "success",
            "data": {"key": "value"},
        }
        storage.save("vlm_responses/test_op", response)

        # Load back
        loaded = storage.load("vlm_responses/test_op")
        assert loaded == response

        # Verify JSON file was created
        json_file = storage.vlm_responses_dir / "response_test_op.json"
        assert json_file.exists()

    def test_save_operation_result(self, storage: DiskStorage) -> None:
        """Test saving operation result as YAML."""
        result = {
            "operation": "clustering",
            "clusters": [
                {"id": 1, "pages": [1, 2, 3]},
                {"id": 2, "pages": [4, 5]},
            ],
        }
        storage.save("results/clustering", result)

        # Load back
        loaded = storage.load("results/clustering")
        assert loaded == result

        # Verify YAML file was created and is valid
        yaml_file = storage.results_dir / "clustering.yaml"
        assert yaml_file.exists()

        with yaml_file.open("r") as f:
            yaml_content = yaml.safe_load(f)
        assert yaml_content == result

    def test_load_default(self, storage: DiskStorage) -> None:
        """Test loading non-existent key returns default."""
        assert storage.load("pages/999", default=None) is None
        assert storage.load("pages/999") is None

    def test_exists(self, storage: DiskStorage) -> None:
        """Test exists method."""
        assert not storage.exists("pages/001")
        storage.save("pages/001", b"data")
        assert storage.exists("pages/001")

    def test_invalid_key_format(self, storage: DiskStorage) -> None:
        """Test that invalid key format raises error."""
        with pytest.raises(ValueError, match="Invalid key format"):
            storage.save("invalid_key", "value")

    def test_unknown_key_type(self, storage: DiskStorage) -> None:
        """Test that unknown key type raises error."""
        with pytest.raises(ValueError, match="Unknown key type"):
            storage.save("unknown_type/name", "value")

    def test_pages_format(self, storage: DiskStorage) -> None:
        """Test that pages are saved as binary files."""
        page_data = b"test_image_data"
        storage.save("pages/001", page_data)

        page_file = storage.pages_dir / "page_001.png"
        assert page_file.exists()
        assert page_file.read_bytes() == page_data

    def test_vlm_responses_format(self, storage: DiskStorage) -> None:
        """Test that VLM responses are saved as JSON."""
        response = {"status": "ok", "data": [1, 2, 3]}
        storage.save("vlm_responses/test", response)

        response_file = storage.vlm_responses_dir / "response_test.json"
        assert response_file.exists()

        with response_file.open("r") as f:
            loaded = json.load(f)
        assert loaded == response

    def test_results_format(self, storage: DiskStorage) -> None:
        """Test that results are saved as YAML."""
        result = {"clusters": 3, "pages": 10}
        storage.save("results/test_result", result)

        result_file = storage.results_dir / "test_result.yaml"
        assert result_file.exists()

        with result_file.open("r") as f:
            loaded = yaml.safe_load(f)
        assert loaded == result


class TestDocumentState:
    """Test suite for DocumentState dataclass."""

    def test_default_creation(self) -> None:
        """Test creating DocumentState with defaults."""
        state = DocumentState()
        assert state.pages == {}
        assert state.vlm_responses == {}
        assert state.operation_results == {}

    def test_with_data(self) -> None:
        """Test creating DocumentState with data."""
        state = DocumentState(
            pages={1: b"page1"},
            vlm_responses={"op1": {"result": "ok"}},
            operation_results={"op1": {"data": "value"}},
        )
        assert len(state.pages) == 1
        assert len(state.vlm_responses) == 1
        assert len(state.operation_results) == 1


class TestStateManager:
    """Test suite for StateManager."""

    @pytest.fixture
    def memory_storage(self) -> MemoryStorage:
        """Create MemoryStorage for testing."""
        return MemoryStorage()

    @pytest.fixture
    def disk_storage(self, tmp_path: Path) -> DiskStorage:
        """Create DiskStorage for testing."""
        return DiskStorage(tmp_path)

    def test_init_with_memory(self, memory_storage: MemoryStorage) -> None:
        """Test StateManager initialization with MemoryStorage."""
        manager = StateManager(memory_storage)
        assert manager.storage == memory_storage
        assert isinstance(manager.state, DocumentState)

    def test_init_with_disk(self, disk_storage: DiskStorage) -> None:
        """Test StateManager initialization with DiskStorage."""
        manager = StateManager(disk_storage)
        assert manager.storage == disk_storage
        assert isinstance(manager.state, DocumentState)

    def test_save_and_load_page_memory(self, memory_storage: MemoryStorage) -> None:
        """Test saving and loading page with MemoryStorage."""
        manager = StateManager(memory_storage)

        # Save page
        page_data = b"test_page_data"
        manager.save_page(1, page_data)

        # Load back
        loaded = manager.load_page(1)
        assert loaded == page_data

        # Check state is updated
        assert manager.state.pages[1] == page_data

    def test_save_and_load_page_disk(self, disk_storage: DiskStorage) -> None:
        """Test saving and loading page with DiskStorage."""
        manager = StateManager(disk_storage)

        # Save page
        page_data = b"test_page_data"
        manager.save_page(1, page_data)

        # Load back
        loaded = manager.load_page(1)
        assert loaded == page_data

        # Verify file exists
        page_file = disk_storage.pages_dir / "page_001.png"
        assert page_file.exists()

    def test_load_nonexistent_page(self, memory_storage: MemoryStorage) -> None:
        """Test loading non-existent page returns None."""
        manager = StateManager(memory_storage)
        assert manager.load_page(999) is None

    def test_save_vlm_response(self, memory_storage: MemoryStorage) -> None:
        """Test saving VLM response."""
        manager = StateManager(memory_storage)

        response = {"operation": "test", "result": "success"}
        manager.save_vlm_response("test_op", response)

        # Check storage
        loaded = manager.storage.load("vlm_responses/test_op")
        assert loaded == response

        # Check state is updated
        assert manager.state.vlm_responses["test_op"] == response

    def test_save_operation_result(self, disk_storage: DiskStorage) -> None:
        """Test saving operation result."""
        manager = StateManager(disk_storage)

        result = {"clusters": 3, "pages": [1, 2, 3]}
        manager.save_operation_result("clustering", result)

        # Check storage
        loaded = manager.storage.load("results/clustering")
        assert loaded == result

        # Check state is updated
        assert manager.state.operation_results["clustering"] == result

        # Verify YAML file
        result_file = disk_storage.results_dir / "clustering.yaml"
        assert result_file.exists()

    def test_save_state(self, memory_storage: MemoryStorage) -> None:
        """Test explicit save_state call (should be no-op for MemoryStorage)."""
        manager = StateManager(memory_storage)

        # Save some data
        manager.save_page(1, b"data")
        manager.save_vlm_response("test", {"result": "ok"})

        # Explicit save (should not raise errors)
        manager.save_state()

        # Data should still be accessible
        assert manager.load_page(1) == b"data"

    def test_multiple_pages(self, memory_storage: MemoryStorage) -> None:
        """Test saving and loading multiple pages."""
        manager = StateManager(memory_storage)

        # Save multiple pages
        pages = {
            1: b"page1_data",
            2: b"page2_data",
            3: b"page3_data",
        }

        for page_num, data in pages.items():
            manager.save_page(page_num, data)

        # Load all pages
        for page_num, expected_data in pages.items():
            loaded = manager.load_page(page_num)
            assert loaded == expected_data

    def test_page_number_formatting(self, disk_storage: DiskStorage) -> None:
        """Test that page numbers are formatted correctly (zero-padded)."""
        manager = StateManager(disk_storage)

        manager.save_page(1, b"data1")
        manager.save_page(10, b"data10")
        manager.save_page(100, b"data100")

        # Check file names are correctly formatted
        assert (disk_storage.pages_dir / "page_001.png").exists()
        assert (disk_storage.pages_dir / "page_010.png").exists()
        assert (disk_storage.pages_dir / "page_100.png").exists()
