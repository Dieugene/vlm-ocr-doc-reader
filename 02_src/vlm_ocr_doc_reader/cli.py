"""CLI interface for document recognition.

This module provides command-line interface for PDF document processing
using FullDescriptionOperation under the hood.
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from .core.processor import DocumentProcessor
from .operations.full_description import FullDescriptionOperation
from .schemas.config import ProcessorConfig

# Configure logging format
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


def setup_logging(log_level: str) -> None:
    """Setup logging configuration.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
    """
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        stream=sys.stdout
    )


def validate_arguments(pdf_path: Path, api_key: Optional[str]) -> None:
    """Validate CLI arguments.

    Args:
        pdf_path: Path to PDF file
        api_key: Gemini API key from environment

    Raises:
        SystemExit: If validation fails
    """
    # Check PDF file exists
    if not pdf_path.exists():
        print(f"Error: PDF file not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    # Check it's a file (not directory)
    if not pdf_path.is_file():
        print(f"Error: Path is not a file: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    # Check API key is set
    if not api_key:
        print(
            "Error: GEMINI_API_KEY not found in environment. "
            "Please set it in .env file or as environment variable.",
            file=sys.stderr
        )
        sys.exit(1)


def create_output_directory(output_dir: Path) -> None:
    """Create output directory if it doesn't exist.

    Args:
        output_dir: Path to output directory
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(__name__)
    logger.info(f"Output directory: {output_dir}")


def main() -> int:
    """Main CLI entry point.

    Parses arguments, validates input, creates DocumentProcessor,
    executes FullDescriptionOperation, and saves results.

    Returns:
        0 on success, 1 on error
    """
    # Parse arguments
    parser = argparse.ArgumentParser(
        description="Recognize PDF documents using VLM and OCR",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  vlm-ocr-reader document.pdf
  vlm-ocr-reader document.pdf --output-dir ./results
  vlm-ocr-reader document.pdf -o ./output --dpi 200
  vlm-ocr-reader document.pdf --log-level DEBUG
        """
    )

    parser.add_argument(
        "pdf_path",
        type=Path,
        help="Path to PDF file to process"
    )

    parser.add_argument(
        "--output-dir", "-o",
        type=Path,
        default=Path("./output"),
        help="Directory for saving results (default: ./output)"
    )

    parser.add_argument(
        "--dpi",
        type=int,
        default=150,
        help="DPI for PDF rendering (default: 150)"
    )

    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)"
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)

    try:
        # Load environment variables
        load_dotenv()

        # Get API key
        api_key = os.getenv("GEMINI_API_KEY")

        # Validate arguments
        validate_arguments(args.pdf_path, api_key)

        # Create output directory
        create_output_directory(args.output_dir)

        # Log startup info
        logger.info(f"Starting processing: {args.pdf_path}")
        logger.info(f"DPI: {args.dpi}")
        logger.info(f"Output directory: {args.output_dir}")

        # Create processor config
        config = ProcessorConfig(
            state_dir=args.output_dir,
            auto_save=True,
            render_dpi=args.dpi,
            log_level=args.log_level
        )

        # Create document processor
        logger.info("Initializing DocumentProcessor...")
        processor = DocumentProcessor(
            source=args.pdf_path,
            config=config
        )
        logger.info(f"Document loaded: {processor.num_pages} pages")

        # Create and execute operation
        logger.info("Starting FullDescriptionOperation...")
        operation = FullDescriptionOperation(processor)
        result = operation.execute()

        # Save result
        processor.state_manager.save_operation_result(
            "full_description",
            {
                "text": result.text,
                "structure": result.structure,
                "tables": result.tables
            }
        )

        # Print summary
        result_path = args.output_dir / "results" / "full_description.yaml"
        print()
        print("=" * 60)
        print("Processing completed successfully!")
        print("=" * 60)
        print(f"Pages processed: {processor.num_pages}")
        print(f"Text length: {len(result.text)} characters")
        print(f"Headers found: {len(result.structure.get('headers', []))}")
        print(f"Results saved to: {result_path}")
        print("=" * 60)

        return 0

    except KeyboardInterrupt:
        logger.info("Processing interrupted by user")
        return 1

    except Exception as e:
        logger.exception(f"Error during processing: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
