"""Experimental probe for Qwen VLM models via DashScope OpenAI-compatible API.

Raw requests.post with minimum payload. Tests several candidate models for
replacing gemini-2.5-flash in the scan step (page text + structure extraction).

Usage:
    python scripts/qwen_vlm_probe.py                         # default model list
    python scripts/qwen_vlm_probe.py qwen3-vl-plus           # single model
    python scripts/qwen_vlm_probe.py qwen3-vl-plus qwen-vl-max
"""

import base64
import io
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

ENDPOINT = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions"
DEFAULT_MODELS = [
    "qwen3-vl-plus",
    "qwen3-vl-flash",
    "qwen-vl-max",
    "qwen2.5-vl-72b-instruct",
]
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def post(payload: dict, api_key: str, timeout: int = 90) -> tuple[int, str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    r = requests.post(ENDPOINT, headers=headers, json=payload, timeout=timeout)
    return r.status_code, r.text


def extract_text(body: str) -> str:
    try:
        data = json.loads(body)
        choices = data.get("choices", [])
        if not choices:
            return body[:200]
        msg = choices[0].get("message", {})
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                p.get("text", "") for p in content if isinstance(p, dict)
            )
        return str(content)[:200]
    except Exception:
        return body[:200]


def probe(label: str, payload: dict, api_key: str) -> bool:
    t0 = time.monotonic()
    try:
        status, body = post(payload, api_key)
    except Exception as e:
        print(f"[{label}] EXC {type(e).__name__}: {str(e)[:160]}")
        return False
    dt = time.monotonic() - t0
    if status == 200:
        print(f"[{label}] 200 OK ({dt:.1f}s) -> {extract_text(body)!r}")
        return True
    snippet = body[:240].replace("\n", " ")
    print(f"[{label}] {status} ({dt:.1f}s) body={snippet}")
    return False


def tiny_png_bytes() -> bytes:
    from PIL import Image
    img = Image.new("RGB", (64, 64), color=(200, 50, 50))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_text_payload(model: str, prompt: str) -> dict:
    return {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }


def make_image_payload(
    model: str, prompt: str, img_bytes: bytes, high_res: bool = False
) -> dict:
    b64 = base64.b64encode(img_bytes).decode("utf-8")
    payload: dict = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    },
                ],
            }
        ],
    }
    if high_res:
        payload["vl_high_resolution_images"] = True
    return payload


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("QWEN_API_KEY")
    if not api_key:
        print("DASHSCOPE_API_KEY / QWEN_API_KEY missing", file=sys.stderr)
        return 1

    models = sys.argv[1:] if len(sys.argv) > 1 else DEFAULT_MODELS

    tiny = tiny_png_bytes()
    print(f"tiny.png size={len(tiny)}B")

    pdf_path = PROJECT_ROOT / "03_data" / "test_document.pdf"
    page_bytes: bytes | None = None
    if pdf_path.exists():
        try:
            import pymupdf
            doc = pymupdf.open(str(pdf_path))
            pix = doc[0].get_pixmap(dpi=150)
            page_bytes = pix.tobytes("png")
            print(f"page1.png size={len(page_bytes)}B (dpi=150)")
        except Exception as e:
            print(f"render skipped: {e}")

    for model in models:
        print(f"\n=== {model} ===")
        probe(
            f"{model}/text-only",
            make_text_payload(model, "Answer with one word: ok"),
            api_key,
        )
        time.sleep(1)
        probe(
            f"{model}/tiny-image",
            make_image_payload(model, "What color? One word.", tiny),
            api_key,
        )
        time.sleep(1)
        if page_bytes is not None:
            probe(
                f"{model}/page1 std",
                make_image_payload(
                    model,
                    "Return the first heading of this page in one line.",
                    page_bytes,
                ),
                api_key,
            )
            time.sleep(2)
            if model == "qwen-vl-max":
                probe(
                    f"{model}/page1 hi-res",
                    make_image_payload(
                        model,
                        "Return the first heading of this page in one line.",
                        page_bytes,
                        high_res=True,
                    ),
                    api_key,
                )
                time.sleep(2)

    return 0


if __name__ == "__main__":
    sys.exit(main())
