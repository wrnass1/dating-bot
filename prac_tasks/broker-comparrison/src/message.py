from __future__ import annotations

import os
import struct
import time
from dataclasses import dataclass


_HEADER_STRUCT = struct.Struct("!QQ")  # sent_time_ns, seq


@dataclass(frozen=True)
class MessageSpec:
    payload_bytes: int


def monotonic_time_ns() -> int:
    return time.monotonic_ns()


def make_message_bytes(spec: MessageSpec, seq: int, *, sent_time_ns: int | None = None) -> bytes:
    if sent_time_ns is None:
        sent_time_ns = monotonic_time_ns()
    payload = os.urandom(spec.payload_bytes)
    return _HEADER_STRUCT.pack(sent_time_ns, seq) + payload


def parse_message_bytes(raw: bytes) -> tuple[int, int, bytes]:
    sent_time_ns, seq = _HEADER_STRUCT.unpack_from(raw, 0)
    return sent_time_ns, seq, raw[_HEADER_STRUCT.size :]
