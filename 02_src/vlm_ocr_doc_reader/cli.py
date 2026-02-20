"""CLI interface for document recognition.

This module provides command-line interface for PDF document processing
using FullDescriptionOperation under the hood.
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from .core.processor import DocumentProcessor
from .operations.full_description import FullDescriptionOperation
from .schemas.config import ProcessorConfig

LOG_FORMAT = "%(asctime)s | %(name)s | %(message)s"
LOG_DATEFMT = "%H:%M:%S"

# Default parent dir for runs
DEFAULT_OUTPUT_DIR = Path(
    r"D:\_storage_cbr\020_docs_vision\08_vlm-ocr-doc-reader\03_data"
)


def setup_logging(log_level: str, log_file: Optional[Path] = None) -> None:
    """Setup logging: console + optional file handler.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Path to log file (UTF-8). If None, console only.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Console handler
    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        datefmt=LOG_DATEFMT,
        stream=sys.stdout,
    )

    # File handler for the run directory
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(level)
        fh.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATEFMT))
        logging.getLogger().addHandler(fh)


def validate_arguments(pdf_path: Path, api_key: Optional[str]) -> None:
    """Validate CLI arguments.

    Raises:
        SystemExit: If validation fails
    """
    if not pdf_path.exists():
        print(f"Error: PDF file not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    if not pdf_path.is_file():
        print(f"Error: Path is not a file: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    if not api_key:
        print(
            "Error: GEMINI_API_KEY not found in environment. "
            "Please set it in .env file or as environment variable.",
            file=sys.stderr,
        )
        sys.exit(1)


def create_run_dir(parent_dir: Path) -> Path:
    """Create timestamped run subdirectory.

    Args:
        parent_dir: Parent directory for runs

    Returns:
        Path to created run directory, e.g. parent_dir/run_2026-02-09_1715/
    """
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    run_dir = parent_dir / f"run_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def main() -> int:
    """Main CLI entry point.

    Returns:
        0 on success, 1 on error
    """
    parser = argparse.ArgumentParser(
        description="Recognize PDF documents using VLM and OCR",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  vlm-ocr-reader document.pdf
  vlm-ocr-reader document.pdf --output-dir ./my_runs
  vlm-ocr-reader document.pdf --dpi 200 --log-level DEBUG

Each run creates a timestamped subdirectory inside --output-dir:
  output-dir/run_2026-02-09_1715/
    cache/pages/       rendered page images
    logs/run.log       full log with OCR request-result pairs
    results/           YAML results
        """,
    )

    parser.add_argument(
        "pdf_path",
        type=Path,
        help="Path to PDF file to process",
    )

    parser.add_argument(
        "--output-dir", "-o",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Parent directory for run folders (default: {DEFAULT_OUTPUT_DIR})",
    )

    parser.add_argument(
        "--dpi",
        type=int,
        default=150,
        help="DPI for PDF rendering (default: 150)",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )

    parser.add_argument(
        "--max-tool-workers",
        type=int,
        default=5,
        help="Max parallel OCR workers per tool batch (default: 5)",
    )

    parser.add_argument(
        "--max-iterations",
        type=int,
        default=100,
        help="Max tool calling iterations per VLM invoke (default: 100)",
    )

    args = parser.parse_args()

    try:
        # Load environment variables
        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY")

        # Validate
        validate_arguments(args.pdf_path, api_key)

        # Create run directory
        run_dir = create_run_dir(args.output_dir)
        log_file = run_dir / "logs" / "run.log"

        # Setup logging: console + file in run dir
        setup_logging(args.log_level, log_file)
        logger = logging.getLogger(__name__)

        logger.info(f"Run directory: {run_dir}")
        logger.info(f"Processing: {args.pdf_path}")
        logger.info(f"DPI: {args.dpi}")

        # Create processor with state_dir = run directory
        config = ProcessorConfig(
            state_dir=run_dir,
            auto_save=True,
            render_dpi=args.dpi,
            log_level=args.log_level,
            max_tool_workers=args.max_tool_workers,
            max_iterations=args.max_iterations,
        )

        logger.info("Initializing DocumentProcessor...")
        processor = DocumentProcessor(
            source=args.pdf_path,
            config=config,
        )
        logger.info(f"Document loaded: {processor.num_pages} pages")

        # Execute operation
        logger.info("Starting FullDescriptionOperation...")
        operation = FullDescriptionOperation(processor)
        result = operation.execute()

        # Save result
        processor.state_manager.save_operation_result(
            "full_description",
            {
                "text": result.text,
                "structure": result.structure,
                "tables": result.tables,
            },
        )

        # Summary
        result_path = run_dir / "results" / "full_description.yaml"
        print()
        print("=" * 60)
        print("Processing completed successfully!")
        print("=" * 60)
        print(f"Run directory:   {run_dir}")
        print(f"Pages processed: {processor.num_pages}")
        print(f"Text length:     {len(result.text or '')} characters")
        print(f"Headers found:   {len(result.structure.get('headers', []))}")
        print(f"Results:         {result_path}")
        print(f"Log:             {log_file}")
        print("=" * 60)

        return 0

    except KeyboardInterrupt:
        print("\nProcessing interrupted by user", file=sys.stderr)
        return 1

    except Exception as e:
        logging.getLogger(__name__).exception(f"Error during processing: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
