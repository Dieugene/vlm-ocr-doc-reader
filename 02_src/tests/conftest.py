"""Root conftest — loads .env and configures file logging to 04_logs/."""

import logging
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (worktree root when using git worktree)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


def is_dashscope_key_valid() -> bool:
    """Return True if DASHSCOPE_API_KEY / QWEN_API_KEY is set and not a dummy."""
    key = (os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY") or "").strip()
    if not key:
        return False
    _DUMMY_KEYS = frozenset({"test", "test-key", "test-api-key-123"})
    return key.lower() not in _DUMMY_KEYS



# === File logging to 04_logs/ ===
LOGS_DIR = _PROJECT_ROOT / "04_logs"
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
