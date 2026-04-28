from __future__ import annotations

import csv
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/summarize_results.py results/matrix_*.csv", file=sys.stderr)
        return 2

    path = Path(sys.argv[1])
    rows = list(csv.DictReader(path.open("r", encoding="utf-8")))
    if not rows:
        print("No rows.", file=sys.stderr)
        return 1

    cols = [
        "broker",
        "payload_bytes",
        "target_msg_per_sec",
        "processed",
        "throughput_msg_s",
        "latency_ms_mean",
        "latency_ms_p95",
        "send_errors",
        "process_errors",
    ]

    def fmt(row: dict, k: str) -> str:
        v = row.get(k, "")
        if k in {"throughput_msg_s", "latency_ms_mean", "latency_ms_p95"}:
            try:
                return f"{float(v):.3f}"
            except Exception:
                return str(v)
        return str(v)

    print("| " + " | ".join(cols) + " |")
    print("|" + "|".join(["---"] * len(cols)) + "|")
    for r in rows:
        print("| " + " | ".join(fmt(r, c) for c in cols) + " |")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

