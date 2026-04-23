"""Grid search over OCR chunk_size on a single scanned workspace.

Reuses an existing scan result (state.json with populated ocr_registry).
For each chunk_size value:
  1. Reset all entries to resolution=0, value=null, context=null
  2. Run DocumentReader.resolve(chunk_size=N)
  3. Snapshot resolved values
  4. Compute metrics

Output: markdown summary + JSON dump of per-entity values across runs for
post-hoc consistency checks.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "02_src"))

from vlm_ocr_doc_reader import DocumentReader


def reset_registry(state_path: Path) -> None:
    data = json.loads(state_path.read_text(encoding="utf-8"))
    for e in data.get("ocr_registry", []):
        e["resolution"] = 0
        e["value"] = None
        e["context"] = None
        e["verified"] = False
        e["confidence"] = None
    data["page_states"] = {}
    state_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def snapshot(state_path: Path) -> dict:
    return json.loads(state_path.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True, type=Path)
    ap.add_argument("--workspace", required=True, type=Path)
    ap.add_argument(
        "--chunks",
        type=str,
        default="1,3,5,8,12",
        help="comma-separated chunk sizes",
    )
    ap.add_argument(
        "--workers",
        type=str,
        default="1",
        help="comma-separated worker counts (parallel chunks)",
    )
    ap.add_argument("--out", type=Path, default=None, help="JSON dump path")
    args = ap.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")

    chunks = sorted(int(c) for c in args.chunks.split(",") if c.strip())
    workers_list = sorted(int(w) for w in args.workers.split(",") if w.strip())
    if not chunks or not workers_list:
        print("Empty chunks or workers list", file=sys.stderr)
        return 1

    doc_dirs = [d for d in args.workspace.iterdir() if d.is_dir()]
    if len(doc_dirs) != 1:
        print(
            f"Expected one document subdir in {args.workspace}, found {len(doc_dirs)}"
        )
        return 1
    state_path = doc_dirs[0] / "state.json"
    if not state_path.exists():
        print(f"state.json not found: {state_path}")
        return 1

    initial = snapshot(state_path)
    n_entries = len(initial.get("ocr_registry", []))
    print(f"registry has {n_entries} entries; chunks={chunks}; workers={workers_list}")

    runs: dict[str, dict] = {}
    combos = [(cs, w) for cs in chunks for w in workers_list]
    for cs, w in combos:
        key = f"chunk={cs},workers={w}"
        print(f"\n=== {key} ===", flush=True)
        reset_registry(state_path)
        reader = DocumentReader.open(args.pdf, args.workspace)
        t0 = time.monotonic()
        reader.resolve(chunk_size=cs, max_workers=w)
        dt = time.monotonic() - t0
        snap = snapshot(state_path)
        reg = snap.get("ocr_registry", [])
        ok = sum(
            1 for e in reg if e["resolution"] >= 1 and (e.get("value") or "").strip()
        )
        nd = sum(
            1 for e in reg if e["resolution"] >= 1 and not (e.get("value") or "").strip()
        )
        un = sum(1 for e in reg if e["resolution"] == 0)
        runs[key] = {
            "chunk_size": cs,
            "workers": w,
            "time_sec": round(dt, 2),
            "ok": ok,
            "no_data": nd,
            "unresolved": un,
            "values": {e["entity_id"]: (e.get("value") or "") for e in reg},
        }
        print(
            f"  time={dt:.1f}s  ok={ok}  no_data={nd}  unresolved={un}",
            flush=True,
        )

    # Baseline = first combo (chunk=min, workers=min)
    base_key = f"chunk={chunks[0]},workers={workers_list[0]}"
    base_vals = runs[base_key]["values"]

    print("\n=== summary ===")
    header = (
        f"{'chunk':>6} {'workers':>8} {'time_s':>8} {'ok':>4} "
        f"{'no_data':>8} {'unresolved':>11} {'consistency':>12}"
    )
    print(header)
    print("-" * len(header))
    for cs, w in combos:
        key = f"chunk={cs},workers={w}"
        r = runs[key]
        if key == base_key:
            cons = "BASELINE"
        else:
            same = sum(
                1
                for eid, v in r["values"].items()
                if base_vals.get(eid) == v
            )
            cons = f"{same}/{n_entries}"
        print(
            f"{cs:>6} {w:>8} {r['time_sec']:>8.1f} {r['ok']:>4} "
            f"{r['no_data']:>8} {r['unresolved']:>11} {cons:>12}"
        )

    out_path = args.out or (PROJECT_ROOT / "04_logs" / "chunk_grid_results.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(runs, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nfull dump: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
