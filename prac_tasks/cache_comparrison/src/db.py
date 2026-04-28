from __future__ import annotations

from dataclasses import dataclass

import psycopg2
from psycopg2.extensions import connection as PgConnection


@dataclass
class DbCounters:
    reads: int = 0
    writes: int = 0

    @property
    def total(self) -> int:
        return self.reads + self.writes


class PostgresStore:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._conn: PgConnection = psycopg2.connect(dsn)
        self._conn.autocommit = True
        self.counters = DbCounters()

    def close(self) -> None:
        self._conn.close()

    def init_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS cache_items (
                    id INTEGER PRIMARY KEY,
                    value INTEGER NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )

    def seed(self, dataset_size: int) -> None:
        with self._conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE cache_items")
            rows = [(item_id, item_id * 10) for item_id in range(1, dataset_size + 1)]
            cur.executemany(
                """
                INSERT INTO cache_items (id, value)
                VALUES (%s, %s)
                """,
                rows,
            )
        self.reset_counters()

    def reset_counters(self) -> None:
        self.counters = DbCounters()

    def read(self, item_id: int) -> int:
        with self._conn.cursor() as cur:
            cur.execute("SELECT value FROM cache_items WHERE id = %s", (item_id,))
            row = cur.fetchone()
        self.counters.reads += 1
        if row is None:
            raise KeyError(f"Item {item_id} not found")
        return int(row[0])

    def write(self, item_id: int, value: int) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                UPDATE cache_items
                SET value = %s, updated_at = NOW()
                WHERE id = %s
                """,
                (value, item_id),
            )
        self.counters.writes += 1
