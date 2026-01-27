"""Thin VLM client wrapper with throttling and retry logic."""

import random
import time
from datetime import datetime
from typing import Dict, List, Optional

import requests

from common.gemini_client import GeminiRestClient

MIN_INTERVAL_S = 0.6
MAX_RETRIES = 3
BACKOFF_BASE = 1.0
BACKOFF_JITTER = 0.3
TIMEOUT_S = 30  # Not used by GeminiRestClient yet; kept for doc/consistency
LOW_DPI = 110
MAX_CALLS_PER_RUN = 50


class VLMClient:
    def __init__(
        self,
        gemini_client: Optional[GeminiRestClient] = None,
        min_interval_s: float = MIN_INTERVAL_S,
        max_retries: int = MAX_RETRIES,
        backoff_base: float = BACKOFF_BASE,
        backoff_jitter: float = BACKOFF_JITTER,
        max_calls_per_run: int = MAX_CALLS_PER_RUN,
        enforce_limit: bool = True,
        run_logger=None,
    ):
        self.client = gemini_client or GeminiRestClient()
        self.min_interval_s = min_interval_s
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_jitter = backoff_jitter
        self.max_calls_per_run = max_calls_per_run
        self.enforce_limit = enforce_limit
        self.run_logger = run_logger
        self._last_call_ts: Optional[float] = None
        self.calls_made: int = 0

    def _log(self, message: str):
        if self.run_logger:
            self.run_logger(message)

    def _throttle(self):
        if self._last_call_ts is None:
            return
        elapsed = time.monotonic() - self._last_call_ts
        if elapsed < self.min_interval_s:
            time.sleep(self.min_interval_s - elapsed)

    def _register_attempt(self):
        self.calls_made += 1
        self._last_call_ts = time.monotonic()
        if self.max_calls_per_run and self.calls_made > self.max_calls_per_run:
            msg = f"VLM call limit exceeded for this run ({self.calls_made}/{self.max_calls_per_run})"
            if self.enforce_limit:
                raise RuntimeError(msg)
            self._log(f"warning: {msg}")

    def generate_content(self, prompt: str, images: List[bytes]) -> Dict:
        attempt = 0
        while attempt < self.max_retries:
            attempt += 1
            self._throttle()
            ts = datetime.now().isoformat()
            started = time.monotonic()
            try:
                response = self.client.generate_content(prompt, images)
                latency = time.monotonic() - started
                self._register_attempt()
                self._log(
                    f"vlm_call ts={ts} attempt={attempt} status=200 latency={latency:.3f}s images={len(images)}"
                )
                return response
            except requests.exceptions.HTTPError as e:
                latency = time.monotonic() - started
                status_code = e.response.status_code if e.response else "error"
                self._register_attempt()
                self._log(
                    f"vlm_call ts={ts} attempt={attempt} status={status_code} latency={latency:.3f}s images={len(images)}"
                )
                if status_code not in {429, 503} or attempt >= self.max_retries:
                    raise
                sleep_for = self.backoff_base * (2 ** (attempt - 1)) + random.uniform(0, self.backoff_jitter)
                time.sleep(sleep_for)
            except Exception as e:  # noqa: BLE001
                latency = time.monotonic() - started
                self._register_attempt()
                self._log(
                    f"vlm_call ts={ts} attempt={attempt} status=error latency={latency:.3f}s images={len(images)} err={e}"
                )
                if attempt >= self.max_retries:
                    raise
                sleep_for = self.backoff_base * (2 ** (attempt - 1)) + random.uniform(0, self.backoff_jitter)
                time.sleep(sleep_for)
        raise RuntimeError("VLM retries exhausted")

