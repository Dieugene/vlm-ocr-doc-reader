"""State management for document processing with memory and disk backends."""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Protocol

import yaml

logger = logging.getLogger(__name__)


class StorageBackend(Protocol):
    """Protocol for state storage backends."""

    def save(self, key: str, value: Any) -> None:
        """Save value by key.

        Args:
            key: Storage key (e.g., "pages/001", "vlm_responses/full_desc")
            value: Value to save (can be bytes, dict, str, etc.)
        """
        ...

    def load(self, key: str, default: Any = None) -> Any:
        """Load value by key.

        Args:
            key: Storage key
            default: Default value if key doesn't exist

        Returns:
            Stored value or default
        """
        ...

    def exists(self, key: str) -> bool:
        """Check if key exists.

        Args:
            key: Storage key

        Returns:
            True if key exists, False otherwise
        """
        ...


class MemoryStorage:
    """In-memory storage backend for experiments and testing."""

    def __init__(self) -> None:
        """Initialize in-memory storage."""
        self._data: Dict[str, Any] = {}
        logger.info("Initialized MemoryStorage backend")

    def save(self, key: str, value: Any) -> None:
        """Save value to in-memory dict."""
        self._data[key] = value
        logger.debug(f"MemoryStorage: saved key '{key}'")

    def load(self, key: str, default: Any = None) -> Any:
        """Load value from in-memory dict."""
        value = self._data.get(key, default)
        logger.debug(f"MemoryStorage: loaded key '{key}' (found: {value is not None})")
        return value

    def exists(self, key: str) -> bool:
        """Check if key exists in in-memory dict."""
        return key in self._data


class DiskStorage:
    """File-based storage backend with JSON/YAML support."""

    def __init__(self, state_dir: Path) -> None:
        """Initialize disk storage with directory structure.

        Args:
            state_dir: Root directory for state storage
        """
        self.state_dir = Path(state_dir)
        self.cache_dir = self.state_dir / "cache"
        self.pages_dir = self.cache_dir / "pages"
        self.vlm_responses_dir = self.cache_dir / "vlm_responses"
        self.results_dir = self.state_dir / "results"
        self.logs_dir = self.state_dir / "logs"

        # Create directory structure
        self._create_directories()

        logger.info(f"Initialized DiskStorage backend at {self.state_dir}")

    def _create_directories(self) -> None:
        """Create state directory structure."""
        for directory in [
            self.cache_dir,
            self.pages_dir,
            self.vlm_responses_dir,
            self.results_dir,
            self.logs_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Created directory: {directory}")

    def _get_file_path(self, key: str) -> tuple[Path, str]:
        """Parse key and determine file path and format.

        Args:
            key: Storage key (e.g., "pages/001", "vlm_responses/full_desc",
                        "results/clustering")

        Returns:
            Tuple of (file_path, format) where format is "binary", "json", or "yaml"
        """
        parts = key.split("/", 1)

        if len(parts) != 2:
            raise ValueError(f"Invalid key format: '{key}'. Expected 'type/name'")

        key_type, name = parts

        if key_type == "pages":
            # PNG images
            filename = f"page_{name}.png"
            return self.pages_dir / filename, "binary"

        elif key_type == "vlm_responses":
            # JSON for VLM responses
            filename = f"response_{name}.json"
            return self.vlm_responses_dir / filename, "json"

        elif key_type == "results":
            # YAML for operation results (human-readable)
            filename = f"{name}.yaml"
            return self.results_dir / filename, "yaml"

        else:
            raise ValueError(f"Unknown key type: '{key_type}'")

    def save(self, key: str, value: Any) -> None:
        """Save value to file based on key type.

        Args:
            key: Storage key
            value: Value to save (bytes for binary, dict for json/yaml)
        """
        file_path, format_type = self._get_file_path(key)

        try:
            if format_type == "binary":
                if not isinstance(value, bytes):
                    raise TypeError(f"Binary save requires bytes, got {type(value)}")
                file_path.write_bytes(value)

            elif format_type == "json":
                with file_path.open("w", encoding="utf-8") as f:
                    json.dump(value, f, ensure_ascii=False, indent=2)

            elif format_type == "yaml":
                with file_path.open("w", encoding="utf-8") as f:
                    yaml.dump(value, f, allow_unicode=True, default_flow_style=False)

            logger.info(f"DiskStorage: saved key '{key}' to {file_path}")

        except Exception as e:
            logger.error(f"DiskStorage: failed to save key '{key}': {e}")
            raise

    def load(self, key: str, default: Any = None) -> Any:
        """Load value from file based on key type.

        Args:
            key: Storage key
            default: Default value if file doesn't exist

        Returns:
            Loaded value or default
        """
        file_path, format_type = self._get_file_path(key)

        if not file_path.exists():
            logger.debug(f"DiskStorage: key '{key}' not found, returning default")
            return default

        try:
            if format_type == "binary":
                value = file_path.read_bytes()

            elif format_type == "json":
                with file_path.open("r", encoding="utf-8") as f:
                    value = json.load(f)

            elif format_type == "yaml":
                with file_path.open("r", encoding="utf-8") as f:
                    value = yaml.safe_load(f)

            logger.debug(f"DiskStorage: loaded key '{key}' from {file_path}")
            return value

        except Exception as e:
            logger.error(f"DiskStorage: failed to load key '{key}': {e}")
            raise

    def exists(self, key: str) -> bool:
        """Check if file exists for given key.

        Args:
            key: Storage key

        Returns:
            True if file exists, False otherwise
        """
        file_path, _ = self._get_file_path(key)
        return file_path.exists()


@dataclass
class DocumentState:
    """Container for document processing state.

    Attributes:
        pages: Mapping of page_num (1-based) to rendered image bytes
        vlm_responses: Mapping of operation name to VLM response dict
        operation_results: Mapping of operation name to result data
    """

    pages: Dict[int, bytes] = field(default_factory=dict)
    vlm_responses: Dict[str, Any] = field(default_factory=dict)
    operation_results: Dict[str, Any] = field(default_factory=dict)


class StateManager:
    """Manager for document state with pluggable storage backend."""

    def __init__(self, storage: StorageBackend) -> None:
        """Initialize state manager with storage backend.

        Args:
            storage: Storage backend (MemoryStorage or DiskStorage)
        """
        self.storage = storage
        self.state = DocumentState(
            pages={},
            vlm_responses={},
            operation_results={},
        )
        logger.info(f"Initialized StateManager with {type(storage).__name__}")

    def save_page(self, page_num: int, image: bytes) -> None:
        """Save rendered page.

        Args:
            page_num: 1-based page number
            image: PNG image bytes
        """
        key = f"pages/{page_num:03d}"
        self.storage.save(key, image)
        self.state.pages[page_num] = image
        logger.debug(f"Saved page {page_num} ({len(image)} bytes)")

    def load_page(self, page_num: int) -> Optional[bytes]:
        """Load rendered page.

        Args:
            page_num: 1-based page number

        Returns:
            PNG image bytes or None if not found
        """
        key = f"pages/{page_num:03d}"
        image = self.storage.load(key, default=None)

        if image is not None:
            self.state.pages[page_num] = image

        return image

    def save_vlm_response(self, operation: str, response: Dict[str, Any]) -> None:
        """Save VLM response.

        Args:
            operation: Operation name (e.g., "full_desc", "clustering")
            response: VLM response dictionary
        """
        key = f"vlm_responses/{operation}"
        self.storage.save(key, response)
        self.state.vlm_responses[operation] = response
        logger.debug(f"Saved VLM response for '{operation}'")

    def save_operation_result(self, operation: str, result: Any) -> None:
        """Save operation result in YAML format.

        Args:
            operation: Operation name (e.g., "clustering", "triage")
            result: Operation result data (will be serialized to YAML)
        """
        key = f"results/{operation}"
        self.storage.save(key, result)
        self.state.operation_results[operation] = result
        logger.info(f"Saved operation result for '{operation}'")

    def save_state(self) -> None:
        """Explicitly save all state to storage.

        For MemoryStorage this is a no-op (data already in memory).
        For DiskStorage this ensures all cached data is persisted.
        """
        logger.info("Explicit state save requested")
        # Note: With current implementation, all data is already saved
        # immediately via save_page/save_vlm_response/save_operation_result
        # This method is provided for future batch-save optimization

    def load_state(self) -> None:
        """Load all state from storage.

        For MemoryStorage this is a no-op (data already in memory).
        For DiskStorage this loads all available data from disk.
        """
        logger.info("Loading all state from storage")
        # Note: This is a simplified implementation
        # Full implementation would scan directories and load all data
        # Current design uses lazy loading via load_page() etc.
