from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import click
from redis import Redis
from redis.exceptions import RedisError

from .bench import init_db, run_benchmark
from .config import PROFILE_READ_RATIO, RunConfig, VALID_STRATEGIES
from .db import PostgresStore


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _check_services(postgres_dsn: str, redis_url: str) -> None:
    try:
        store = PostgresStore(postgres_dsn)
    except Exception as exc:  # noqa: BLE001
        raise click.ClickException(
            "PostgreSQL is unavailable. Start the containers first with "
            "`docker compose up -d`, then retry. "
            f"DSN: {postgres_dsn}. Original error: {exc}"
        ) from exc
    else:
        store.close()

    try:
        redis_client = Redis.from_url(redis_url, decode_responses=True)
        redis_client.ping()
    except RedisError as exc:
        raise click.ClickException(
            "Redis is unavailable. Start the containers first with "
            "`docker compose up -d`, then retry. "
            f"URL: {redis_url}. Original error: {exc}"
        ) from exc


def _make_config(
    strategy: str,
    profile: str,
    duration_s: float,
    dataset_size: int,
    key_space: int,
    redis_url: str,
    postgres_dsn: str,
    seed: int,
) -> RunConfig:
    return RunConfig(
        strategy=strategy,
        profile=profile,
        duration_s=duration_s,
        dataset_size=dataset_size,
        key_space=key_space,
        redis_url=redis_url,
        postgres_dsn=postgres_dsn,
        seed=seed,
    )


@click.group()
def cli() -> None:
    pass


@cli.command("init-db")
@click.option("--dataset-size", type=int, default=1000, show_default=True)
@click.option("--redis-url", type=str, default="redis://localhost:6380/0", show_default=True)
@click.option(
    "--postgres-dsn",
    type=str,
    default="dbname=cache_lab user=app password=app host=localhost port=5434",
    show_default=True,
)
def init_db_cmd(dataset_size: int, redis_url: str, postgres_dsn: str) -> None:
    _check_services(postgres_dsn, redis_url)
    cfg = RunConfig(
        strategy="cache-aside",
        profile="balanced",
        dataset_size=dataset_size,
        redis_url=redis_url,
        postgres_dsn=postgres_dsn,
    )
    init_db(cfg)
    click.echo(f"Database initialized with {dataset_size} rows")


@cli.command("run")
@click.option("--strategy", type=click.Choice(sorted(VALID_STRATEGIES)), required=True)
@click.option("--profile", type=click.Choice(sorted(PROFILE_READ_RATIO)), required=True)
@click.option("--duration-s", type=float, default=20.0, show_default=True)
@click.option("--dataset-size", type=int, default=1000, show_default=True)
@click.option("--key-space", type=int, default=200, show_default=True)
@click.option("--seed", type=int, default=42, show_default=True)
@click.option("--redis-url", type=str, default="redis://localhost:6380/0", show_default=True)
@click.option(
    "--postgres-dsn",
    type=str,
    default="dbname=cache_lab user=app password=app host=localhost port=5434",
    show_default=True,
)
@click.option("--out-json", type=click.Path(dir_okay=False, path_type=Path), default=None)
@click.option("--out-csv", type=click.Path(dir_okay=False, path_type=Path), default=None)
def run_cmd(
    strategy: str,
    profile: str,
    duration_s: float,
    dataset_size: int,
    key_space: int,
    seed: int,
    redis_url: str,
    postgres_dsn: str,
    out_json: Path | None,
    out_csv: Path | None,
) -> None:
    _check_services(postgres_dsn, redis_url)
    cfg = _make_config(strategy, profile, duration_s, dataset_size, key_space, redis_url, postgres_dsn, seed)
    result = run_benchmark(cfg)
    payload = result.to_dict()

    click.echo(
        f"strategy={strategy} profile={profile} throughput={payload['throughput_req_s']:.2f} req/s "
        f"latency_mean={payload['latency_ms_mean']:.3f} ms db_total={payload['db_total_ops']} "
        f"cache_hit_rate={payload['cache_hit_rate']:.3f}"
    )

    if out_json is None and out_csv is None:
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if out_json is not None:
        _ensure_parent(out_json)
        out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if out_csv is not None:
        _ensure_parent(out_csv)
        write_header = not out_csv.exists()
        with out_csv.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(payload.keys()))
            if write_header:
                writer.writeheader()
            writer.writerow(payload)


@cli.command("matrix")
@click.option("--duration-s", type=float, default=20.0, show_default=True)
@click.option("--dataset-size", type=int, default=1000, show_default=True)
@click.option("--key-space", type=int, default=200, show_default=True)
@click.option("--seed", type=int, default=42, show_default=True)
@click.option("--redis-url", type=str, default="redis://localhost:6380/0", show_default=True)
@click.option(
    "--postgres-dsn",
    type=str,
    default="dbname=cache_lab user=app password=app host=localhost port=5434",
    show_default=True,
)
@click.option("--out-dir", type=click.Path(file_okay=False, path_type=Path), default=Path("results"))
def matrix_cmd(
    duration_s: float,
    dataset_size: int,
    key_space: int,
    seed: int,
    redis_url: str,
    postgres_dsn: str,
    out_dir: Path,
) -> None:
    _check_services(postgres_dsn, redis_url)
    stamp = _utc_stamp()
    out_dir = out_dir.resolve()
    out_csv = out_dir / f"matrix_{stamp}.csv"
    out_jsonl = out_dir / f"matrix_{stamp}.jsonl"
    _ensure_parent(out_csv)
    _ensure_parent(out_jsonl)

    plan = [(strategy, profile) for strategy in sorted(VALID_STRATEGIES) for profile in PROFILE_READ_RATIO]
    click.echo(f"Planned runs: {len(plan)}")

    fieldnames: list[str] | None = None
    with out_csv.open("a", newline="", encoding="utf-8") as csv_file, out_jsonl.open("a", encoding="utf-8") as jsonl_file:
        writer: csv.DictWriter | None = None
        for index, (strategy, profile) in enumerate(plan, start=1):
            click.echo(f"[{index}/{len(plan)}] strategy={strategy} profile={profile}")
            cfg = _make_config(strategy, profile, duration_s, dataset_size, key_space, redis_url, postgres_dsn, seed)
            result = run_benchmark(cfg)
            row = result.to_dict()
            jsonl_file.write(json.dumps(row, ensure_ascii=False) + "\n")
            jsonl_file.flush()
            if fieldnames is None:
                fieldnames = list(row.keys())
                writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
                writer.writeheader()
            assert writer is not None
            writer.writerow(row)
            csv_file.flush()
            click.echo(
                f"  throughput={row['throughput_req_s']:.2f} req/s latency_mean={row['latency_ms_mean']:.3f} ms "
                f"db_total={row['db_total_ops']} cache_hit_rate={row['cache_hit_rate']:.3f}"
            )

    click.echo(f"Wrote {out_csv}")
    click.echo(f"Wrote {out_jsonl}")


if __name__ == "__main__":
    cli()
