"""UUIDv7 identifier generation (RFC 9562) — the single identifier system.

Per ADR-0013 / technology-baseline: UUIDv7 generated **application-side** (the
database stores plain ``uuid``; no extension or DB function required, keeping
the schema portable across Supabase and local Compose).

Properties used by this project:
- 48-bit big-endian Unix-ms timestamp → lexicographically sortable keys
  (B-tree locality for the event-heavy later phases; FR-70 event ordering).
- Uniqueness from 74 bits of randomness (monotonic counter in the rand_a
  field guards same-ms collisions).
- Serialized as canonical lowercase 8-4-4-4-12 hex; API representation is
  the string form of the same UUID (no second identifier system).

Do NOT use ``uuid1``/``uuid4`` for new entity ids — this module is the sole
generator so id ordering assumptions remain valid everywhere.
"""

from __future__ import annotations

import os
import time
import uuid

_INT_MASK_12 = 0x0FFF
_INT_MASK_62 = (1 << 62) - 1
_SEQ_COUNTER = 0  # process-local monotonic sequence for same-ms uniqueness


def uuid7() -> uuid.UUID:
    """Generate a RFC 9562 UUIDv7 with millisecond timestamp + monotonic seq."""
    global _SEQ_COUNTER
    ts_ms = time.time_ns() // 1_000_000
    rand_a = _SEQ_COUNTER & _INT_MASK_12  # 12-bit same-ms sequence
    _SEQ_COUNTER += 1
    rand_b = int.from_bytes(os.urandom(8), "big") & _INT_MASK_62
    value = (ts_ms & ((1 << 48) - 1)) << 80
    value |= 0x7 << 76  # version 7
    value |= rand_a << 64
    value |= 0b10 << 62  # RFC 4122 variant
    value |= rand_b
    return uuid.UUID(int=value)


def new_id() -> str:
    """Canonical string form used in DTOs and APIs."""
    return str(uuid7())
