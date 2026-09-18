"""Caching for model output.

The cache key is the whole provenance of a result. If any part of it changes — the
specification, the slice of context, the provider, the model string, the prompt template
version, or the task — it is a different answer and must be recomputed. That is what
makes "regenerate and compare" meaningful rather than a coin flip.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

MAX_ENTRIES = 256
DEFAULT_TTL_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class CacheKey:
    spec_fingerprint: str
    context_fingerprint: str
    provider: str
    model: str
    prompt_template_version: str
    task: str

    def digest(self) -> str:
        raw = "|".join(
            (
                self.spec_fingerprint,
                self.context_fingerprint,
                self.provider,
                self.model,
                self.prompt_template_version,
                self.task,
            )
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def describe(self) -> dict[str, str]:
        return {
            "spec": self.spec_fingerprint[:19],
            "context": self.context_fingerprint[:19],
            "provider": self.provider,
            "model": self.model,
            "prompt_template_version": self.prompt_template_version,
            "task": self.task,
        }


def context_fingerprint(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


class ResultCache:
    """A small in-process LRU with a TTL. Deliberately not persisted across restarts:
    stale semantic analysis is more confusing than a second of recomputation."""

    def __init__(self, *, max_entries: int = MAX_ENTRIES, ttl: float = DEFAULT_TTL_SECONDS) -> None:
        self._entries: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self.max_entries = max_entries
        self.ttl = ttl
        self.hits = 0
        self.misses = 0

    def get(self, key: CacheKey) -> Any | None:
        digest = key.digest()
        record = self._entries.get(digest)
        if record is None:
            self.misses += 1
            return None
        stored_at, value = record
        if time.time() - stored_at > self.ttl:
            self._entries.pop(digest, None)
            self.misses += 1
            return None
        self._entries.move_to_end(digest)
        self.hits += 1
        return value

    def put(self, key: CacheKey, value: Any) -> None:
        digest = key.digest()
        self._entries[digest] = (time.time(), value)
        self._entries.move_to_end(digest)
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)

    def clear(self) -> int:
        removed = len(self._entries)
        self._entries.clear()
        self.hits = 0
        self.misses = 0
        return removed

    def stats(self) -> dict[str, Any]:
        total = self.hits + self.misses
        return {
            "entries": len(self._entries),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hits / total, 3) if total else 0.0,
            "ttl_seconds": self.ttl,
        }
