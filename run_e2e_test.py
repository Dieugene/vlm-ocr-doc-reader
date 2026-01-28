#!/usr/bin/env python3
"""
Сквозной тест vlm-ocr-doc-reader с реальными API.

Этот скрипт:
1. Создает тестовый PDF документ
2. Обрабатывает через DocumentProcessor
3. Выполняет FullDescriptionOperation
4. Проверяет результат

Требования:
- .env файл с GEMINI_API_KEY
- Установленные зависимости (pip install -r requirements.txt)
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "02_src"))

from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def check_env():
    """Проверить наличие API ключей."""
    gemini_key = os.getenv("GEMINI_API_KEY")

    if not gemini_key:
        print("[ERROR] GEMINI_API_KEY not found in .env")
        print("Create .env file with:")
        print("GEMINI_API_KEY=your_actual_key_here")
        return False

    print("[OK] GEMINI_API_KEY found")
    return True


def create_test_pdf():
    """Создать тестовый PDF документ."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import inch

        pdf_path = Path(__file__).parent / "03_data" / "test_document.pdf"
        pdf_path.parent.mkdir(parents=True, exist_ok=True)

        # Create PDF with multiple pages and headers
        c = canvas.Canvas(str(pdf_path), pagesize=letter)

        # Page 1 - Title
        c.setFont("Helvetica-Bold", 18)
        c.drawString(1 * inch, 10 * inch, "Test Document")
        c.setFont("Helvetica", 12)
        c.drawString(1 * inch, 9 * inch, "This is a test document for VLM OCR processing.")
        c.drawString(1 * inch, 8.5 * inch, "It contains multiple pages with headers and structure.")

        # Page 2 - Section 1
        c.showPage()
        c.setFont("Helvetica-Bold", 16)
        c.drawString(1 * inch, 10 * inch, "1. Introduction")
        c.setFont("Helvetica", 12)
        c.drawString(1 * inch, 9 * inch, "This is the introduction section.")
        c.drawString(1 * inch, 8.5 * inch, "It explains the purpose of the document.")

        # Page 3 - Subsection
        c.showPage()
        c.setFont("Helvetica-Bold", 14)
        c.drawString(1 * inch, 10 * inch, "1.1. Background")
        c.setFont("Helvetica", 12)
        c.drawString(1 * inch, 9 * inch, "Background information goes here.")
        c.drawString(1 * inch, 8.5 * inch, "This provides context for the main content.")

        # Page 4 - Section 2
        c.showPage()
        c.setFont("Helvetica-Bold", 16)
        c.drawString(1 * inch, 10 * inch, "2. Main Content")
        c.setFont("Helvetica", 12)
        c.drawString(1 * inch, 9 * inch, "This is the main content section.")
        c.drawString(1 * inch, 8.5 * inch, "It contains the core information.")

        c.save()

        print(f"[OK] Test PDF created: {pdf_path}")
        return pdf_path

    except ImportError:
        print("[ERROR] reportlab not installed")
        print("Install: pip install reportlab")
        return None
    except Exception as e:
        print(f"[ERROR] Failed to create PDF: {e}")
        return None


def run_e2e_test():
    """Запустить сквозной тест."""
    print("\n" + "="*60)
    print("END-TO-END TEST VLM-OCR-DOC-READER")
    print("="*60 + "\n")

    # Check environment
    if not check_env():
        return False

    # Create test PDF
    pdf_path = create_test_pdf()
    if not pdf_path:
        return False

    try:
        from vlm_ocr_doc_reader.core.processor import DocumentProcessor
        from vlm_ocr_doc_reader.core.vlm_client import GeminiVLMClient, VLMConfig
        from vlm_ocr_doc_reader.operations import FullDescriptionOperation

        print("\n[INFO] Initializing DocumentProcessor...")

        # Initialize VLM client
        vlm_config = VLMConfig(
            api_key=os.getenv("GEMINI_API_KEY"),
            model="gemini-2.5-flash"
        )
        vlm_client = GeminiVLMClient(vlm_config)

        # Initialize processor with PDF (stateless mode)
        processor = DocumentProcessor(
            source=pdf_path,
            vlm_client=vlm_client
        )

        print(f"[OK] DocumentProcessor created")
        print(f"   Pages: {processor.num_pages}")

        # Execute FullDescriptionOperation
        print("\n[INFO] Executing FullDescriptionOperation...")
        operation = FullDescriptionOperation(processor)

        result = operation.execute()

        print("\n[OK] FullDescriptionOperation completed")

        # Display results
        print("\n" + "="*60)
        print("RESULTS:")
        print("="*60)

        print(f"\n[TEXT] First 500 characters:")
        print(result.text[:500] + "..." if len(result.text) > 500 else result.text)

        print(f"\n[STRUCTURE] Headers:")
        if "headers" in result.structure:
            for header in result.structure["headers"]:
                level_prefix = "#" * header.get("level", 1)
                print(f"   {level_prefix} {header.get('title', 'N/A')} (page {header.get('page', 'N/A')})")
        else:
            print("   No headers found")

        print(f"\n[TABLES] Count: {len(result.tables)}")
        for table in result.tables:
            print(f"   - {table.get('id', 'N/A')}: {table.get('type', 'N/A')}")

        print("\n" + "="*60)
        print("[SUCCESS] TEST PASSED!")
        print("="*60 + "\n")

        return True

    except Exception as e:
        print(f"\n[ERROR] Execution failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_e2e_test()
    sys.exit(0 if success else 1)
