from __future__ import annotations

import asyncio
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

import click

from .bench import run_benchmark
from .config import RunConfig


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


@click.group()
def cli() -> None:
    pass


@cli.command("run")
@click.option("--broker", type=click.Choice(["rabbitmq", "redis"]), required=True)
@click.option("--duration-s", type=float, default=20.0, show_default=True)
@click.option("--producers", type=int, default=1, show_default=True)
@click.option("--consumers", type=int, default=1, show_default=True)
@click.option("--rps", "target_msg_per_sec", type=int, default=1000, show_default=True)
@click.option("--payload-bytes", type=int, default=128, show_default=True)
@click.option("--out-json", type=click.Path(dir_okay=False, path_type=Path), default=None)
@click.option("--out-csv", type=click.Path(dir_okay=False, path_type=Path), default=None)
def run_cmd(
    broker: str,
    duration_s: float,
    producers: int,
    consumers: int,
    target_msg_per_sec: int,
    payload_bytes: int,
    out_json: Path | None,
    out_csv: Path | None,
) -> None:
    cfg = RunConfig(
        broker=broker,
        duration_s=duration_s,
        producers=producers,
        consumers=consumers,
        target_msg_per_sec=target_msg_per_sec,
        payload_bytes=payload_bytes,
    )

    result = asyncio.run(run_benchmark(cfg))
    data = result.to_dict()

    if out_json is None and out_csv is None:
        click.echo(json.dumps(data, ensure_ascii=False, indent=2))
        return

    if out_json is not None:
        _ensure_parent(out_json)
        out_json.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if out_csv is not None:
        _ensure_parent(out_csv)
        write_header = not out_csv.exists()
        with out_csv.open("a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(data.keys()))
            if write_header:
                w.writeheader()
            w.writerow(data)


@cli.command("matrix")
@click.option("--duration-s", type=float, default=20.0, show_default=True)
@click.option(
    "--budget-s",
    type=float,
    default=None,
    help="Total time budget for the whole matrix (seconds). If set, per-run duration is auto-reduced to fit roughly within the budget.",
)
@click.option("--producers", type=int, default=1, show_default=True)
@click.option("--consumers", type=int, default=1, show_default=True)
@click.option(
    "--payload-bytes",
    type=str,
    default="128,1024,10240,102400",
    show_default=True,
    help="Comma-separated payload sizes in bytes",
)
@click.option(
    "--rps",
    type=str,
    default="1000,5000,10000",
    show_default=True,
    help="Comma-separated target message/sec values",
)
@click.option(
    "--quick",
    is_flag=True,
    help="Quick preset: payload-bytes=128,10240 and rps=1000,10000 (still runs both brokers).",
)
@click.option("--out-dir", type=click.Path(file_okay=False, path_type=Path), default=Path("results"))
def matrix_cmd(
    duration_s: float,
    budget_s: float | None,
    producers: int,
    consumers: int,
    payload_bytes: str,
    rps: str,
    quick: bool,
    out_dir: Path,
) -> None:
    if quick:
        payloads = [128, 10240]
        rps_values = [1000, 10000]
    else:
        payloads = [int(x.strip()) for x in payload_bytes.split(",") if x.strip()]
        rps_values = [int(x.strip()) for x in rps.split(",") if x.strip()]
    stamp = _utc_stamp()

    out_dir = out_dir.resolve()
    out_csv = out_dir / f"matrix_{stamp}.csv"
    out_jsonl = out_dir / f"matrix_{stamp}.jsonl"
    _ensure_parent(out_csv)
    _ensure_parent(out_jsonl)

    plan = [(broker, pbytes, target) for broker in ("rabbitmq", "redis") for pbytes in payloads for target in rps_values]
    total = len(plan)

    # Fit into a rough wall-time budget by shrinking per-run duration.
    # Overhead exists (connections, setup), so we aim at ~80% of the budget for sleep time.
    if budget_s is not None and budget_s > 0 and total > 0:
        target_per_run = max(0.5, (budget_s * 0.8) / total)
        if target_per_run < duration_s:
            duration_s = target_per_run

    click.echo(f"Planned runs: {total} (brokers=2 × payloads={len(payloads)} × rps={len(rps_values)})")
    click.echo(f"Expected wall time (rough): ~{total * duration_s:.0f}s + overhead")

    fieldnames: list[str] | None = None
    with out_jsonl.open("a", encoding="utf-8") as jf, out_csv.open("a", newline="", encoding="utf-8") as cf:
        w: csv.DictWriter | None = None
        try:
            t_all0 = perf_counter()
            for idx, (broker, pbytes, target) in enumerate(plan, start=1):
                t0 = perf_counter()
                click.echo(f"[{idx}/{total}] broker={broker} payload={pbytes}B rps={target} duration={duration_s}s ...")

                cfg = RunConfig(
                    broker=broker,
                    duration_s=duration_s,
                    producers=producers,
                    consumers=consumers,
                    target_msg_per_sec=target,
                    payload_bytes=pbytes,
                )
                try:
                    result = asyncio.run(run_benchmark(cfg))
                except KeyboardInterrupt:
                    click.echo("Aborted by user, partial results were saved.")
                    break

                row = result.to_dict()

                jf.write(json.dumps(row, ensure_ascii=False) + "\n")
                jf.flush()

                if fieldnames is None:
                    fieldnames = list(row.keys())
                    w = csv.DictWriter(cf, fieldnames=fieldnames)
                    w.writeheader()
                assert w is not None
                w.writerow(row)
                cf.flush()

                elapsed_one = perf_counter() - t0
                elapsed_all = perf_counter() - t_all0
                remaining = total - idx
                eta = (elapsed_all / idx) * remaining if idx else 0.0
                click.echo(
                    f"  done in {elapsed_one:.1f}s; processed={row.get('processed')} throughput={float(row.get('throughput_msg_s', 0.0)):.1f} msg/s; ETA ~{eta:.0f}s"
                )
        except KeyboardInterrupt:
            click.echo("Aborted by user, partial results were saved.")

    click.echo(f"Wrote {out_csv}")
    click.echo(f"Wrote {out_jsonl}")


if __name__ == "__main__":
    cli()

