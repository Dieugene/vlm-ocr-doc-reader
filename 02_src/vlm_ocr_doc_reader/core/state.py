"""State management for document processing with memory and disk backends."""

import hashlib
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Protocol, TypedDict

import yaml

logger = logging.getLogger(__name__)

# --- Resolution Levels (ADR-001) ---
ResolutionLevel = Literal[0, 1, 2]
PageResolution = Literal["none", "scan", "resolved", "verified"]

_VALID_PAGE_RESOLUTIONS: frozenset[str] = frozenset(
    {"none", "scan", "resolved", "verified"}
)


def _validate_resolution(value: Any) -> ResolutionLevel:
    """Validate and coerce resolution to 0|1|2."""
    if value in (0, 1, 2):
        return value  # type: ignore[return-value]
    try:
        v = int(value)
        if 0 <= v <= 2:
            return v  # type: ignore[return-value]
    except (TypeError, ValueError):
        pass
    return 0


def _validate_page_resolution(value: Any) -> Optional[PageResolution]:
    """Validate page resolution string."""
    if isinstance(value, str) and value in _VALID_PAGE_RESOLUTIONS:
        return value  # type: ignore[return-value]
    return None


@dataclass
class OCRRegistryEntry:
    """Single OCR entity entry for Resolution Levels.

    Attributes:
        page_num: 1-based page number
        entity_id: Unique identifier (key for upsert)
        prompt: Extraction prompt
        resolution: Current level (0=scan, 1=resolved, 2=verified)
        value: Extracted value (filled at Resolve)
        context: Context (filled at Resolve)
        verified: Passed verification (Level 2)
        confidence: Verification result (e.g. "3/3")
    """

    page_num: int
    entity_id: str
    prompt: str
    resolution: ResolutionLevel = 0
    value: Optional[str] = None
    context: Optional[str] = None
    verified: bool = False
    confidence: Optional[str] = None


class VerifyResult(TypedDict, total=False):
    """Contract for verification result (Level 2). Used by future majority-voting strategy."""

    page_num: int
    entity_id: str
    verified: bool
    confidence: str


def group_registry_by_page(
    entries: List[OCRRegistryEntry],
) -> Dict[int, List[OCRRegistryEntry]]:
    """Group OCR registry entries by page_num.

    Args:
        entries: List of OCR registry entries

    Returns:
        Dict mapping page_num to list of entries for that page
    """
    result: Dict[int, List[OCRRegistryEntry]] = {}
    for entry in entries:
        result.setdefault(entry.page_num, []).append(entry)
    return result


def apply_ocr_result(
    entry: OCRRegistryEntry,
    value: Optional[str],
    context: Optional[str],
    resolution: ResolutionLevel = 1,
) -> OCRRegistryEntry:
    """Create updated entry with OCR result applied.

    Args:
        entry: Original registry entry
        value: Extracted value (or empty string for no_data)
        context: Context text (or from explanation for no_data)
        resolution: Resolution level (default 1 for resolved)

    Returns:
        New OCRRegistryEntry with updated value, context, resolution
    """
    return OCRRegistryEntry(
        page_num=entry.page_num,
        entity_id=entry.entity_id,
        prompt=entry.prompt,
        resolution=resolution,
        value=value if value is not None else "",
        context=context,
        verified=entry.verified,
        confidence=entry.confidence,
    )


@dataclass
class DocumentMetadata:
    """Document metadata for Resolution Levels."""

    source_path: Optional[str] = None
    content_hash: Optional[str] = None
    pages_total: int = 0
    created_at: Optional[str] = None  # ISO 8601


@dataclass
class ResolutionDocumentState:
    """Document state for Resolution Levels (DocumentState v2).

    Alias: DocumentState (resolution-level) per ADR-001.
    """

    page_states: Dict[int, PageResolution] = field(default_factory=dict)
    ocr_registry: List[OCRRegistryEntry] = field(default_factory=list)
    metadata: DocumentMetadata = field(default_factory=DocumentMetadata)


def _registry_to_dict(entries: List[OCRRegistryEntry]) -> List[dict]:
    """Serialize OCR registry to list of dicts."""
    return [asdict(e) for e in entries]


def _registry_from_dict(data: List[dict]) -> List[OCRRegistryEntry]:
    """Deserialize OCR registry from list of dicts. Validates resolution, page_num."""
    result: List[OCRRegistryEntry] = []
    for d in data or []:
        row = dict(d)
        try:
            page_num = int(row.get("page_num", 0))
        except (TypeError, ValueError):
            page_num = 0
        if page_num < 1:
            logger.warning(f"Skipping registry entry with invalid page_num={page_num}")
            continue
        result.append(
            OCRRegistryEntry(
                page_num=page_num,
                entity_id=row.get("entity_id", ""),
                prompt=row.get("prompt", ""),
                resolution=_validate_resolution(row.get("resolution", 0)),
                value=row.get("value"),
                context=row.get("context"),
                verified=bool(row.get("verified", False)),
                confidence=row.get("confidence"),
            )
        )
    return result


def _resolution_state_to_dict(state: ResolutionDocumentState) -> dict:
    """Serialize ResolutionDocumentState to dict (page_states keys as strings)."""
    return {
        "page_states": {str(k): v for k, v in state.page_states.items()},
        "ocr_registry": _registry_to_dict(state.ocr_registry),
        "metadata": asdict(state.metadata),
    }


def _resolution_state_from_dict(data: dict) -> ResolutionDocumentState:
    """Deserialize ResolutionDocumentState from dict. Validates page_states values."""
    data = data or {}
    page_states_raw = data.get("page_states") or {}
    page_states: Dict[int, PageResolution] = {}
    for k, v in page_states_raw.items():
        try:
            page_num = int(k)
        except (TypeError, ValueError):
            continue
        if page_num < 1:
            continue
        valid_status = _validate_page_resolution(v)
        if valid_status is not None:
            page_states[page_num] = valid_status
        else:
            logger.warning(f"Skipping invalid page_states value for page {k}: {v!r}")
    ocr_registry = _registry_from_dict(data.get("ocr_registry") or [])
    meta = data.get("metadata") or {}
    metadata = DocumentMetadata(
        source_path=meta.get("source_path"),
        content_hash=meta.get("content_hash"),
        pages_total=meta.get("pages_total", 0),
        created_at=meta.get("created_at"),
    )
    return ResolutionDocumentState(
        page_states=page_states,
        ocr_registry=ocr_registry,
        metadata=metadata,
    )


# --- Workspace (ADR-001) ---

_CHUNK_SIZE = 65536  # 64KB for hashing large files


def compute_content_hash(pdf_path: Path) -> str:
    """Compute SHA256 hex digest of file content.

    Reads file in 64KB chunks for memory efficiency with large PDFs.
    Supports empty files (returns hash of b"").

    Args:
        pdf_path: Path to PDF file

    Returns:
        64-character hex string (full SHA256 digest)
    """
    hash_obj = hashlib.sha256()
    with pdf_path.open("rb") as f:
        while chunk := f.read(_CHUNK_SIZE):
            hash_obj.update(chunk)
    return hash_obj.hexdigest()


def build_document_subdir_name(pdf_path: Path, content_hash: str) -> str:
    """Build document subdirectory name: stem_hash6.

    Sanitizes stem for Windows-safe directory names (replaces /\\:*?\"<>| with _).

    Args:
        pdf_path: Path to PDF file
        content_hash: Full SHA256 hex digest (64 chars)

    Returns:
        {stem}_{hash6} where hash6 is first 6 chars of content_hash
    """
    stem = pdf_path.stem
    sanitized = re.sub(r'[\\/:*?"<>|]', "_", stem)
    hash6 = content_hash[:6]
    return f"{sanitized}_{hash6}"


@dataclass(frozen=True)
class WorkspacePaths:
    """Paths for a document workspace (ADR-001)."""

    workspace_root: Path
    document_dir: Path
    pages_dir: Path
    state_json: Path
    registry_json: Path


class WorkspaceStorage:
    """Workspace storage for document state (ADR-001).

    One workspace serves multiple documents via subdirs {stem}_{content_hash6}.
    """

    def __init__(self, paths: WorkspacePaths) -> None:
        self._paths = paths

    @classmethod
    def from_pdf(cls, pdf_path: Path, workspace: Path) -> "WorkspaceStorage":
        """Create WorkspaceStorage from PDF path and workspace root.

        Computes content_hash, builds document subdir. Does not create directories.
        """
        content_hash = compute_content_hash(pdf_path)
        subdir_name = build_document_subdir_name(pdf_path, content_hash)
        document_dir = Path(workspace) / subdir_name
        paths = WorkspacePaths(
            workspace_root=Path(workspace),
            document_dir=document_dir,
            pages_dir=document_dir / "pages",
            state_json=document_dir / "state.json",
            registry_json=document_dir / "registry.json",
        )
        return cls(paths)

    @property
    def paths(self) -> WorkspacePaths:
        return self._paths

    def ensure_initialized(self) -> None:
        """Create document_dir, pages/, vlm_responses/, results/. Create empty state.json and registry.json if missing."""
        doc_dir = self._paths.document_dir
        doc_dir.mkdir(parents=True, exist_ok=True)
        self._paths.pages_dir.mkdir(parents=True, exist_ok=True)
        (doc_dir / "vlm_responses").mkdir(parents=True, exist_ok=True)
        (doc_dir / "results").mkdir(parents=True, exist_ok=True)

        if not self._paths.state_json.exists():
            empty_state = {
                "page_states": {},
                "ocr_registry": [],
                "metadata": {
                    "source_path": None,
                    "content_hash": None,
                    "pages_total": 0,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            }
            with self._paths.state_json.open("w", encoding="utf-8") as f:
                json.dump(empty_state, f, ensure_ascii=False, indent=2)
        if not self._paths.registry_json.exists():
            with self._paths.registry_json.open("w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)

    def load_state_json(self) -> dict:
        """Load state.json. Returns {} if missing."""
        if not self._paths.state_json.exists():
            return {}
        with self._paths.state_json.open("r", encoding="utf-8") as f:
            return json.load(f)

    def save_state_json(self, payload: dict) -> None:
        """Save state.json."""
        with self._paths.state_json.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def load_registry_json(self) -> list[dict]:
        """Load registry.json. Returns [] if missing."""
        if not self._paths.registry_json.exists():
            return []
        with self._paths.registry_json.open("r", encoding="utf-8") as f:
            return json.load(f)

    def save_registry_json(self, payload: list[dict]) -> None:
        """Save registry.json."""
        with self._paths.registry_json.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)


class WorkspaceBackend:
    """StorageBackend implementation for workspace (ADR-001)."""

    def __init__(self, workspace_storage: WorkspaceStorage) -> None:
        self._ws = workspace_storage
        self._paths = workspace_storage.paths

    def _get_file_path(self, key: str) -> tuple[Path, str]:
        """Map storage key to file path and format. Sanitizes name to prevent path traversal."""
        parts = key.split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid key format: '{key}'. Expected 'type/name'")
        key_type, name = parts

        def _safe_name(n: str) -> str:
            """Extract safe filename, reject path traversal."""
            safe = Path(n).name
            if safe in (".", ".."):
                raise ValueError(f"Invalid name for storage: '{n}'")
            return safe

        if key_type == "document_state":
            return self._paths.state_json, "json"
        elif key_type == "ocr_registry":
            return self._paths.registry_json, "json"
        elif key_type == "pages":
            return self._paths.pages_dir / f"page_{_safe_name(name)}.png", "binary"
        elif key_type == "vlm_responses":
            return self._paths.document_dir / "vlm_responses" / f"response_{_safe_name(name)}.json", "json"
        elif key_type == "results":
            return self._paths.document_dir / "results" / f"{_safe_name(name)}.yaml", "yaml"
        else:
            raise ValueError(f"Unknown key type: '{key_type}'")

    def save(self, key: str, value: Any) -> None:
        file_path, format_type = self._get_file_path(key)
        file_path.parent.mkdir(parents=True, exist_ok=True)
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
            logger.debug(f"WorkspaceBackend: saved key '{key}' to {file_path}")
        except Exception as e:
            logger.error(f"WorkspaceBackend: failed to save key '{key}': {e}")
            raise

    def load(self, key: str, default: Any = None) -> Any:
        file_path, format_type = self._get_file_path(key)
        if not file_path.exists():
            return default
        try:
            if format_type == "binary":
                return file_path.read_bytes()
            elif format_type == "json":
                with file_path.open("r", encoding="utf-8") as f:
                    return json.load(f)
            elif format_type == "yaml":
                with file_path.open("r", encoding="utf-8") as f:
                    return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"WorkspaceBackend: failed to load key '{key}': {e}")
            raise

    def exists(self, key: str) -> bool:
        file_path, _ = self._get_file_path(key)
        return file_path.exists()


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

        if key_type == "document_state":
            # Resolution state (state.json in state_dir root)
            return self.state_dir / "state.json", "json"

        elif key_type == "ocr_registry":
            # OCR Registry (registry.json in state_dir root)
            return self.state_dir / "registry.json", "json"

        elif key_type == "pages":
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
        self._resolution_state = ResolutionDocumentState(
            page_states={},
            ocr_registry=[],
            metadata=DocumentMetadata(),
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

    def load_operation_result(self, operation: str, default: Any = None) -> Any:
        """Load operation result from storage (YAML format).

        Args:
            operation: Operation name (e.g., "full_description", "clustering")
            default: Default value if result not found

        Returns:
            Loaded result dict or default
        """
        key = f"results/{operation}"
        return self.storage.load(key, default=default)

    # --- Resolution Levels API (ADR-001) ---

    def save_document_state(self, state: ResolutionDocumentState) -> None:
        """Save resolution document state.

        Args:
            state: ResolutionDocumentState to persist
        """
        self._resolution_state = state
        data = _resolution_state_to_dict(state)
        self.storage.save("document_state/state", data)
        logger.debug("Saved resolution document state")

    def load_document_state(self) -> ResolutionDocumentState:
        """Load resolution document state. Returns empty state if not found."""
        data = self.storage.load("document_state/state", default=None)
        if data is None:
            self._resolution_state = ResolutionDocumentState(
                page_states={},
                ocr_registry=[],
                metadata=DocumentMetadata(),
            )
            return self._resolution_state
        self._resolution_state = _resolution_state_from_dict(data)
        return self._resolution_state

    def save_ocr_registry(self, entries: List[OCRRegistryEntry]) -> None:
        """Save entire OCR registry. Syncs state.json (single source of truth)."""
        self._resolution_state.ocr_registry = list(entries)
        # C1: state.json is source of truth — always persist full state
        self.save_document_state(self._resolution_state)
        # Keep registry.json in sync for consistency
        data = _registry_to_dict(entries)
        self.storage.save("ocr_registry/registry", data)
        logger.debug(f"Saved OCR registry ({len(entries)} entries)")

    def load_ocr_registry(self) -> List[OCRRegistryEntry]:
        """Load OCR registry. Prefer state.json (source of truth), fallback to registry.json."""
        # C1: state.json is source of truth — load from it when available
        state_data = self.storage.load("document_state/state", default=None)
        if state_data is not None:
            self._resolution_state = _resolution_state_from_dict(state_data)
            return list(self._resolution_state.ocr_registry)
        data = self.storage.load("ocr_registry/registry", default=None)
        if data is None:
            return []
        entries = _registry_from_dict(data)
        self._resolution_state.ocr_registry = entries
        return entries

    def upsert_ocr_entries(self, entries: List[OCRRegistryEntry]) -> int:
        """Merge entries by entity_id. Update if exists, append if new. Skips empty entity_id (H2). Returns count of changed/added."""
        # Ensure we have loaded state
        if not self._resolution_state.ocr_registry and self.storage.exists(
            "document_state/state"
        ):
            self.load_document_state()
        elif not self._resolution_state.ocr_registry and self.storage.exists(
            "ocr_registry/registry"
        ):
            self.load_ocr_registry()
        registry = self._resolution_state.ocr_registry
        by_id: Dict[str, int] = {e.entity_id: i for i, e in enumerate(registry)}
        count = 0
        for entry in entries:
            if not entry.entity_id:
                logger.warning("Skipping upsert for entry with empty entity_id")
                continue
            if entry.entity_id in by_id:
                idx = by_id[entry.entity_id]
                registry[idx] = entry
                count += 1
            else:
                registry.append(entry)
                by_id[entry.entity_id] = len(registry) - 1
                count += 1
        self.save_ocr_registry(registry)
        return count

    def pending_entities(
        self, page_num: Optional[int] = None
    ) -> List[OCRRegistryEntry]:
        """Return entities with resolution < 1 (not yet resolved). Optionally filter by page_num."""
        if not self._resolution_state.ocr_registry and self.storage.exists(
            "document_state/state"
        ):
            self.load_document_state()
        elif not self._resolution_state.ocr_registry and self.storage.exists(
            "ocr_registry/registry"
        ):
            self.load_ocr_registry()
        registry = self._resolution_state.ocr_registry
        result = [e for e in registry if e.resolution < 1]
        if page_num is not None:
            result = [e for e in result if e.page_num == page_num]
        return list(result)

    def set_page_resolution(self, page_num: int, status: PageResolution) -> None:
        """Update page_states[page_num] and persist."""
        if not self._resolution_state.page_states and self.storage.exists(
            "document_state/state"
        ):
            self.load_document_state()
        self._resolution_state.page_states[page_num] = status
        self.save_document_state(self._resolution_state)
        logger.debug(f"Set page {page_num} resolution to {status}")

    def page_status(self) -> Dict[int, PageResolution]:
        """Return copy of page_states."""
        if not self._resolution_state.page_states and self.storage.exists(
            "document_state/state"
        ):
            self.load_document_state()
        return dict(self._resolution_state.page_states)

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


def open_document(
    pdf_path: Path,
    workspace: Optional[Path],
) -> tuple[StateManager, bool]:
    """Open document and return StateManager with appropriate backend.

    Args:
        pdf_path: Path to PDF file
        workspace: Workspace root directory, or None for memory-only

    Returns:
        (state_manager, loaded_existing_state) where loaded_existing_state is True
        if document_dir and state.json existed before initialization
    """
    if workspace is None:
        return StateManager(MemoryStorage()), False

    ws = WorkspaceStorage.from_pdf(pdf_path, Path(workspace))
    loaded_existing = ws.paths.document_dir.exists() and ws.paths.state_json.exists()
    ws.ensure_initialized()
    backend = WorkspaceBackend(ws)
    return StateManager(backend), loaded_existing
