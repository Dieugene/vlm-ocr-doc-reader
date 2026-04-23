"""DocumentReader - Public API for document processing (ADR-001)."""

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

from .state import (
    StateManager,
    open_document,
    OCRRegistryEntry,
    PageResolution,
    group_registry_by_page,
    apply_ocr_result,
)
from .processor import DocumentProcessor
from ..schemas.config import ProcessorConfig
from ..schemas.document import DocumentData
from ..operations.scan import (
    SCAN_PROMPT_TEXT,
    parse_scan_response,
    normalize_scan_registry,
)

logger = logging.getLogger(__name__)


class DocumentReader:
    """Public API for document lifecycle and Resolution Levels (ADR-001).

    Single entry point for CLI, programmatic API, and integrations.
    Manages document state, delegates to DocumentProcessor and StateManager.
    """

    def __init__(
        self,
        pdf_path: Path,
        workspace: Optional[Path],
        state_manager: StateManager,
        processor: DocumentProcessor,
    ) -> None:
        """Initialize DocumentReader (use open() factory)."""
        self._pdf_path = Path(pdf_path)
        self._workspace = Path(workspace) if workspace is not None else None
        self._state_manager = state_manager
        self._processor = processor

    @classmethod
    def open(
        cls,
        pdf_path: Union[Path, str],
        workspace: Optional[Union[Path, str]] = None,
    ) -> "DocumentReader":
        """Open document in memory or workspace mode.

        Args:
            pdf_path: Path to PDF file
            workspace: Workspace root directory, or None for memory-only

        Returns:
            DocumentReader instance

        Raises:
            FileNotFoundError: If PDF file does not exist
            ValueError: If DASHSCOPE_API_KEY (or QWEN_API_KEY) is not set
        """
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF file not found: {path}")
        if not path.is_file():
            raise FileNotFoundError(f"Path is not a file: {path}")

        ws_path = Path(workspace) if workspace is not None else None
        state_manager, _ = open_document(path, ws_path)

        config = ProcessorConfig(
            state_dir=None,
            auto_save=True,
            render_dpi=150,
        )
        processor = DocumentProcessor(
            source=path,
            state_manager=state_manager,
            config=config,
        )

        return cls(
            pdf_path=path,
            workspace=ws_path,
            state_manager=state_manager,
            processor=processor,
        )

    def _normalize_pages(self, pages: Optional[Iterable[int]]) -> List[int]:
        """Normalize pages: None -> all pages, else validate and sort."""
        if pages is None:
            return list(range(1, self._processor.num_pages + 1))
        result = []
        for p in pages:
            try:
                n = int(p)
                if 1 <= n <= self._processor.num_pages:
                    result.append(n)
                else:
                    logger.warning(f"Page {n} out of range [1, {self._processor.num_pages}], skipping")
            except (TypeError, ValueError):
                logger.warning(f"Invalid page value {p!r}, skipping")
        return sorted(set(result))

    def _ensure_pages_rendered(self) -> None:
        """Ensure pages are rendered. Processor renders on init."""
        if self._processor.num_pages == 0:
            logger.warning("Document has no pages")
        # Pages are already rendered by DocumentProcessor during open()

    @staticmethod
    def _scan_batch_size() -> int:
        """Get scan batch size from env to avoid oversized VLM requests."""
        raw = os.getenv("VLM_SCAN_BATCH_SIZE", "2").strip()
        try:
            value = int(raw)
            return value if value > 0 else 2
        except ValueError:
            return 2

    def scan(self, pages: Optional[Iterable[int]] = None) -> None:
        """Level 0: VLM-only scan. Reads pages via VLM, extracts text/structure, produces OCR Registry.

        No OCR calls. Updates page_states to 'scan', upserts OCR Registry, saves for get_document_data().
        """
        page_list = self._normalize_pages(pages)
        self._ensure_pages_rendered()
        if not page_list:
            logger.warning("scan: no pages to process")
            return

        page_to_image = {p.index: p.image for p in self._processor.pages}
        batch_size = self._scan_batch_size()
        all_entries: List[OCRRegistryEntry] = []
        all_text_chunks: List[str] = []
        all_headers: List[dict] = []

        vlm_agent = self._processor.vlm_agent
        vlm_agent.set_system_prompt(SCAN_PROMPT_TEXT)

        for i in range(0, len(page_list), batch_size):
            batch_pages = page_list[i:i + batch_size]
            images: List[bytes] = []
            for page_num in batch_pages:
                img = page_to_image.get(page_num)
                if img is not None:
                    images.append(img)

            if len(images) != len(batch_pages):
                logger.warning(
                    f"scan: expected {len(batch_pages)} images, got {len(images)} "
                    f"for batch {batch_pages}"
                )

            image_to_page = ", ".join(
                f"изображение #{i + 1} — страница {p}"
                for i, p in enumerate(batch_pages)
            )
            user_prompt = (
                f"Тебе передано {len(batch_pages)} изображений в следующем порядке: "
                f"{image_to_page}. Это и есть соответствие между позицией изображения "
                "в запросе и номером страницы документа. Маркер [G{N}] в левом верхнем "
                "углу каждой картинки — проверочный индикатор того же номера. "
                "Для КАЖДОЙ записи в ocr_registry обязательно укажи page_num строго из "
                f"списка {batch_pages}, соответствующий той картинке, на которой это "
                "значение физически видно. Не приписывай сущности со второй картинки "
                "первой и наоборот. Верни JSON в указанном формате."
            )
            response = vlm_agent.invoke_no_tools(user_prompt, images)
            text = response.get("text")
            if text is None:
                error = response.get("error", "Unknown error")
                logger.error(f"scan: VLM failed for batch {batch_pages}: {error}")
                raise RuntimeError(f"scan failed for pages {batch_pages}: {error}")

            payload = parse_scan_response(text)
            fallback_page = batch_pages[0] if len(batch_pages) == 1 else None
            entries = normalize_scan_registry(
                payload.get("ocr_registry") or [],
                fallback_page=fallback_page,
            )
            all_entries.extend(entries)
            chunk_text = payload.get("text") or ""
            if chunk_text:
                all_text_chunks.append(chunk_text)
            structure = payload.get("structure") or {}
            headers = structure.get("headers")
            if isinstance(headers, list):
                all_headers.extend(headers)

            for page_num in batch_pages:
                self._state_manager.set_page_resolution(page_num, "scan")

        if all_entries:
            self._state_manager.upsert_ocr_entries(all_entries)

        self._state_manager.save_operation_result(
            "full_description",
            {
                "text": "\n\n".join(all_text_chunks).strip(),
                "structure": {"headers": all_headers},
                "tables": [],
            },
        )
        logger.info(
            f"scan: {len(page_list)} pages, {len(all_entries)} registry entries, "
            f"batch_size={batch_size}"
        )

    @staticmethod
    def _default_chunk_size() -> int:
        """Default OCR chunk size: env OCR_CHUNK_SIZE or 5."""
        raw = os.getenv("OCR_CHUNK_SIZE", "5").strip()
        try:
            value = int(raw)
            return value if value > 0 else 5
        except ValueError:
            return 5

    @staticmethod
    def _default_max_workers() -> int:
        """Default OCR concurrency: env OCR_MAX_WORKERS or 5."""
        raw = os.getenv("OCR_MAX_WORKERS", "5").strip()
        try:
            value = int(raw)
            return value if value > 0 else 5
        except ValueError:
            return 5

    def resolve(
        self,
        pages: Optional[Iterable[int]] = None,
        chunk_size: Optional[int] = None,
        max_workers: Optional[int] = None,
    ) -> None:
        """Level 1: OCR resolve without VLM. Multi-question per request, parallel chunks.

        Pending entities are grouped by page and split into chunks of
        `chunk_size` prompts. Each chunk is one OCR call (image + N tasks).
        Chunks across all pages execute in a thread pool of `max_workers`
        concurrent workers.

        Defaults: chunk_size from env OCR_CHUNK_SIZE or 5;
                  max_workers from env OCR_MAX_WORKERS or 5.
        """
        ocr_tool = getattr(self._processor, "ocr_tool", None)
        if ocr_tool is None:
            logger.warning(
                "resolve: OCR tool not available (DASHSCOPE_API_KEY not set). Skipping."
            )
            return

        ocr_client = getattr(ocr_tool, "ocr_client", None)
        if ocr_client is None or not hasattr(ocr_client, "extract_batch"):
            logger.warning("resolve: OCR client missing extract_batch, skipping")
            return

        page_list = self._normalize_pages(pages)
        pending = self._state_manager.pending_entities(page_num=None)
        if page_list:
            pending = [e for e in pending if e.page_num in page_list]
        if not pending:
            logger.info(f"resolve: no pending entities for pages {page_list}")
            return

        effective_chunk = chunk_size if chunk_size and chunk_size > 0 else self._default_chunk_size()
        effective_workers = max_workers if max_workers and max_workers > 0 else self._default_max_workers()
        self._resolve_entities(pending, ocr_client, effective_chunk, effective_workers)

    def _resolve_entities(
        self,
        pending: List[OCRRegistryEntry],
        ocr_client: Any,
        chunk_size: int,
        max_workers: int,
    ) -> None:
        """Execute OCR for pending entities in parallel chunks across pages."""
        from .ocr_client import QwenClientError

        by_page = group_registry_by_page(pending)
        page_nums = sorted(by_page.keys())

        # Build all (page_num, image, chunk) tasks across all pages
        tasks: List[Tuple[int, bytes, List[OCRRegistryEntry]]] = []
        for page_num in page_nums:
            entries = by_page[page_num]
            image = self._state_manager.load_page(page_num)
            if image is None:
                logger.warning(f"resolve: page {page_num} not found, skipping")
                continue
            for start in range(0, len(entries), chunk_size):
                tasks.append((page_num, image, entries[start:start + chunk_size]))

        if not tasks:
            logger.info("resolve: nothing to do after task assembly")
            return

        def run_one(
            task: Tuple[int, bytes, List[OCRRegistryEntry]],
        ) -> Tuple[int, List[OCRRegistryEntry], Optional[List[Dict[str, Any]]], Optional[str]]:
            page_num, image, chunk = task
            prompts = [e.prompt for e in chunk]
            try:
                results = ocr_client.extract_batch(image, prompts, page_num)
                return page_num, chunk, results, None
            except QwenClientError as exc:
                return page_num, chunk, None, f"QwenClientError: {exc}"
            except Exception as exc:
                return page_num, chunk, None, f"{type(exc).__name__}: {exc}"

        # Group results by page so set_page_resolution fires once per page
        page_updates: Dict[int, List[OCRRegistryEntry]] = {p: [] for p in page_nums}
        page_any_success: Dict[int, bool] = {p: False for p in page_nums}
        total_calls = 0

        if max_workers <= 1:
            iter_results = (run_one(t) for t in tasks)
        else:
            pool = ThreadPoolExecutor(max_workers=max_workers)
            iter_results = pool.map(run_one, tasks)

        try:
            for page_num, chunk, results, err in iter_results:
                total_calls += 1
                if err is not None:
                    logger.warning(
                        f"resolve: OCR error for page={page_num} "
                        f"chunk_size={len(chunk)}: {err}"
                    )
                    continue

                if len(results) != len(chunk):
                    logger.warning(
                        f"resolve: result count mismatch for page={page_num} "
                        f"(got {len(results)}, expected {len(chunk)})"
                    )

                for entry, result in zip(chunk, results):
                    status = result.get("status", "error")
                    if status in ("ok", "no_data"):
                        value = result.get("value", "") or ""
                        context = result.get("context") or result.get("explanation") or ""
                        page_updates[page_num].append(
                            apply_ocr_result(entry, value, context, resolution=1)
                        )
                        page_any_success[page_num] = True
                    else:
                        logger.warning(
                            f"resolve: status={status} for entity {entry.entity_id} "
                            f"page={page_num}, keeping pending"
                        )
        finally:
            if max_workers > 1:
                pool.shutdown(wait=True)

        # Persist per page (single state.json save per page)
        for page_num in page_nums:
            updated = page_updates.get(page_num) or []
            if updated:
                self._state_manager.upsert_ocr_entries(updated)
            if page_any_success.get(page_num):
                self._state_manager.set_page_resolution(page_num, "resolved")

        logger.info(
            f"resolve: processed {len(page_nums)} pages in {total_calls} OCR calls "
            f"(chunk_size={chunk_size}, max_workers={max_workers})"
        )

    def verify(self, pages: Optional[Iterable[int]] = None) -> None:
        """Level 2 interface only. No majority-voting strategy in v0.2.0 (ADR-001).

        Accepts pages, normalizes range. Empty/invalid range: early exit, state unchanged.
        TODO: Majority voting / confidence scoring deferred until experiments (ADR-001, Task 015).
        """
        page_list = self._normalize_pages(pages)
        if not page_list:
            logger.warning("verify: no pages to process (empty or invalid range)")
            return
        # Stub: no OCR calls, no state changes. Strategy deferred (ADR-001).
        logger.info(f"verify: pages {page_list} (interface stub, voting strategy deferred)")

    def page_status(self) -> Dict[int, PageResolution]:
        """Return page resolution status from StateManager."""
        return self._state_manager.page_status()

    def pending_entities(self, page: Optional[int] = None) -> List[OCRRegistryEntry]:
        """Return pending OCR entities (resolution < 1). Optionally filter by page."""
        return self._state_manager.pending_entities(page_num=page)

    def get_document_data(self) -> DocumentData:
        """Return latest known document data for integration compatibility.

        Loads from storage via StateManager.load_operation_result if available.
        Otherwise returns empty DocumentData.
        """
        data = self._state_manager.load_operation_result("full_description", default=None)
        if data is None or not isinstance(data, dict):
            return DocumentData(text="", structure={"headers": []}, tables=[])

        text = data.get("text") or ""
        structure = data.get("structure")
        if structure is None or not isinstance(structure, dict):
            structure = {"headers": []}
        else:
            headers = structure.get("headers")
            if headers is None or not isinstance(headers, list):
                structure = {**structure, "headers": []}
        tables = data.get("tables")
        if tables is None or not isinstance(tables, list):
            tables = []

        return DocumentData(text=text, structure=structure, tables=tables)
