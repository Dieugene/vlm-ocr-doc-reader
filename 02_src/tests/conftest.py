"""Root conftest — loads .env and configures file logging to 04_logs/."""

import logging
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# === File logging to 04_logs/ ===
LOGS_DIR = Path(r"D:\_storage_cbr\020_docs_vision\08_vlm-ocr-doc-reader\04_logs")
LOGS_DIR.mkdir(parents=True, exist_ok=True)

_ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
_log_file = LOGS_DIR / f"run_{_ts}.log"

_file_handler = logging.FileHandler(_log_file, encoding="utf-8")
_file_handler.setLevel(logging.INFO)
_file_handler.setFormatter(logging.Formatter(
    "%(asctime)s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
))

# Attach to the root logger of the project so ALL modules write there
logging.getLogger("vlm_ocr_doc_reader").addHandler(_file_handler)
logging.getLogger("vlm_ocr_doc_reader").setLevel(logging.INFO)
