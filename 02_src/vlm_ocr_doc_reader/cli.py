"""CLI v2 for document recognition (ADR-001 Resolution Levels).

Subcommands: scan, resolve, verify, full-description.
Uses DocumentReader as single entry point.
"""

import argparse
import io
import logging
import os
import sys
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

from .core.reader import DocumentReader

LOG_FORMAT = "%(asctime)s | %(name)s | %(message)s"
LOG_DATEFMT = "%H:%M:%S"


def ensure_utf8_stdio() -> None:
    """Replace stdout/stderr with UTF-8 wrappers on Windows (cp1251 console).

    Avoids UnicodeEncodeError when printing Unicode to Windows console.
    Call at the very start of main() before any print/log.
    """
    if sys.platform != "win32":
        return
    enc = getattr(sys.stdout, "encoding", None)
    if enc and enc.lower() == "utf-8":
        return
    try:
        if hasattr(sys.stdout, "buffer"):
            sys.stdout = io.TextIOWrapper(
                sys.stdout.buffer, encoding="utf-8", errors="replace"
            )
        if hasattr(sys.stderr, "buffer"):
            sys.stderr = io.TextIOWrapper(
                sys.stderr.buffer, encoding="utf-8", errors="replace"
            )
    except (AttributeError, OSError):
        pass


def parse_pages_arg(raw: Optional[str]) -> Optional[List[int]]:
    """Parse --pages string like '1,2,5-7' into sorted list of page numbers.

    Args:
        raw: Comma-separated numbers and ranges (e.g. "1,2,5-7")

    Returns:
        Sorted list of unique page numbers, or None if raw is None/empty (all pages)

    Raises:
        ValueError: If format is invalid (e.g. "1-2-3", "abc")
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None

    result: set[int] = set()
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            parts = token.split("-", 1)
            if len(parts) != 2:
                raise ValueError(f"Invalid page range: {token!r}")
            try:
                lo, hi = int(parts[0].strip()), int(parts[1].strip())
            except ValueError:
                raise ValueError(f"Invalid page range: {token!r}")
            if lo > hi:
                raise ValueError(f"Invalid page range (lo > hi): {token!r}")
            result.update(range(lo, hi + 1))
        else:
            try:
                result.add(int(token))
            except ValueError:
                raise ValueError(f"Invalid page number: {token!r}")

    if not result:
        return None
    return sorted(result)


def setup_logging(log_level: str) -> None:
    """Setup logging to console (UTF-8 after ensure_utf8_stdio)."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        datefmt=LOG_DATEFMT,
        stream=sys.stdout,
        force=True,
    )


def _check_api_key() -> None:
    """Check DASHSCOPE_API_KEY (or QWEN_API_KEY). Exit with 1 if missing."""
    load_dotenv()
    api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY")
    if not api_key:
        print(
            "Error: DASHSCOPE_API_KEY (or QWEN_API_KEY) not found in environment. "
            "Please set it in .env file or as environment variable.",
            file=sys.stderr,
        )
        sys.exit(1)


def _check_pdf_path(pdf_path: Path) -> None:
    """Validate PDF path. Exit with 1 if invalid."""
    if not pdf_path.exists():
        print(f"Error: PDF file not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)
    if not pdf_path.is_file():
        print(f"Error: Path is not a file: {pdf_path}", file=sys.stderr)
        sys.exit(1)


def validate_arguments(pdf_path: Path, api_key: Optional[str]) -> None:
    """Validate CLI arguments. Raises SystemExit(1) if invalid.

    Kept for test compatibility.
    """
    if not pdf_path.exists():
        print(f"Error: PDF file not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)
    if not pdf_path.is_file():
        print(f"Error: Path is not a file: {pdf_path}", file=sys.stderr)
        sys.exit(1)
    if not api_key:
        print(
            "Error: DASHSCOPE_API_KEY (or QWEN_API_KEY) not found in environment. "
            "Please set it in .env file or as environment variable.",
            file=sys.stderr,
        )
        sys.exit(1)


def cmd_scan(args: argparse.Namespace) -> int:
    """Level 0: VLM-only scan."""
    _check_api_key()
    _check_pdf_path(args.pdf_path)

    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)

    try:
        pages = parse_pages_arg(args.pages) if args.pages else None
        reader = DocumentReader.open(args.pdf_path, args.workspace)
        reader.scan(pages=pages)
        status = reader.page_status()
        logger.info(f"scan: {len(status)} pages processed")
        print(f"Scan completed. Pages: {list(status.keys())}")
        return 0
    except Exception as e:
        logger.exception(f"scan failed: {e}")
        return 1


def cmd_resolve(args: argparse.Namespace) -> int:
    """Level 1: OCR resolve from Registry."""
    _check_api_key()
    _check_pdf_path(args.pdf_path)

    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)

    try:
        pages = parse_pages_arg(args.pages) if args.pages else None
        reader = DocumentReader.open(args.pdf_path, args.workspace)
        reader.resolve(
            pages=pages,
            chunk_size=args.chunk_size,
            max_workers=args.max_workers,
        )
        logger.info("resolve completed")
        print("Resolve completed.")
        return 0
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        logger.exception(f"resolve failed: {e}")
        return 1


def cmd_verify(args: argparse.Namespace) -> int:
    """Level 2: Verify (stub for 015)."""
    _check_api_key()
    _check_pdf_path(args.pdf_path)

    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)

    try:
        pages = parse_pages_arg(args.pages) if args.pages else None
        reader = DocumentReader.open(args.pdf_path, args.workspace)
        reader.verify(pages=pages)
        logger.info("verify completed (stub)")
        print("Verify completed (strategy stub for 015).")
        return 0
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        logger.exception(f"verify failed: {e}")
        return 1


def cmd_full_description(args: argparse.Namespace) -> int:
    """Scan + resolve all pages (backward compatibility)."""
    _check_api_key()
    _check_pdf_path(args.pdf_path)

    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)

    try:
        reader = DocumentReader.open(args.pdf_path, args.workspace)
        reader.scan()
        reader.resolve()
        data = reader.get_document_data()
        logger.info("full-description completed")
        print("Full-description completed.")
        print(f"Text length: {len(data.text or '')} characters")
        print(f"Headers: {len(data.structure.get('headers', []))}")
        return 0
    except Exception as e:
        logger.exception(f"full-description failed: {e}")
        return 1


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    """Add common arguments to subparser."""
    parser.add_argument(
        "pdf_path",
        type=Path,
        help="Path to PDF file",
    )
    parser.add_argument(
        "--workspace",
        "-w",
        type=Path,
        default=None,
        help="Workspace directory for persistent state (memory mode if omitted)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )


def _add_pages_arg(parser: argparse.ArgumentParser) -> None:
    """Add --pages argument for scan/resolve/verify."""
    parser.add_argument(
        "--pages",
        type=str,
        default=None,
        help="Page filter: comma-separated numbers and ranges, e.g. 1,2,5-7",
    )


def main() -> int:
    """Main CLI entry point. Subcommands: scan, resolve, verify, full-description."""
    ensure_utf8_stdio()

    parser = argparse.ArgumentParser(
        description="VLM OCR Document Reader - scan, resolve, verify, full-description",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  vlm-ocr-reader scan document.pdf --workspace ./ws
  vlm-ocr-reader resolve document.pdf -w ./ws --pages 1,3-5
  vlm-ocr-reader verify document.pdf
  vlm-ocr-reader full-description document.pdf
        """,
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # scan
    p_scan = subparsers.add_parser("scan", help="Level 0: VLM-only scan")
    _add_common_args(p_scan)
    _add_pages_arg(p_scan)
    p_scan.set_defaults(func=cmd_scan)

    # resolve
    p_resolve = subparsers.add_parser("resolve", help="Level 1: OCR resolve from Registry")
    _add_common_args(p_resolve)
    _add_pages_arg(p_resolve)
    p_resolve.add_argument(
        "--chunk-size",
        type=int,
        default=None,
        help="OCR chunk size: number of prompts per request (default: env OCR_CHUNK_SIZE or 5)",
    )
    p_resolve.add_argument(
        "--max-workers",
        type=int,
        default=None,
        help="Parallel OCR workers (default: env OCR_MAX_WORKERS or 5)",
    )
    p_resolve.set_defaults(func=cmd_resolve)

    # verify
    p_verify = subparsers.add_parser("verify", help="Level 2: Verify (stub)")
    _add_common_args(p_verify)
    _add_pages_arg(p_verify)
    p_verify.set_defaults(func=cmd_verify)

    # full-description
    p_full = subparsers.add_parser(
        "full-description",
        help="Scan + resolve all pages (backward compatibility)",
    )
    _add_common_args(p_full)
    p_full.set_defaults(func=cmd_full_description)

    args = parser.parse_args()

    try:
        return args.func(args)
    except SystemExit as e:
        return int(e.code) if e.code is not None else 1
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
