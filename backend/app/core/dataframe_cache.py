"""
In-process DataFrame cache (LRU, mtime-validated).

Every query used to re-read and re-parse the processed dataset file from disk.
This cache keeps the most recently used DataFrames in memory, keyed on the
file path and invalidated automatically when the file's mtime changes (i.e.
after re-cleaning). Returns defensive copies so downstream mutation can never
poison the cache.

Single-process by design — same tradeoff as the rate limiter. If the app moves
to multiple workers, this still works correctly per-process (mtime validation
keeps them consistent); a shared Redis cache only becomes worthwhile at that
point for memory efficiency, not correctness.
"""
from __future__ import annotations

import os
import threading
from collections import OrderedDict
from typing import Optional

import pandas as pd


class DataFrameCache:
    def __init__(self, max_items: int = 12):
        self.max_items = max_items
        self._store: OrderedDict[str, tuple] = OrderedDict()   # path -> (mtime, df)
        self._lock = threading.Lock()

    def get(self, path) -> Optional[pd.DataFrame]:
        key = str(path)
        try:
            mtime = os.path.getmtime(key)
        except OSError:
            return None
        with self._lock:
            item = self._store.get(key)
            if item is None or item[0] != mtime:
                if item is not None:
                    del self._store[key]   # stale
                return None
            self._store.move_to_end(key)
            return item[1].copy()

    def put(self, path, df: pd.DataFrame) -> None:
        key = str(path)
        try:
            mtime = os.path.getmtime(key)
        except OSError:
            return
        with self._lock:
            self._store[key] = (mtime, df.copy())
            self._store.move_to_end(key)
            while len(self._store) > self.max_items:
                self._store.popitem(last=False)

    def invalidate(self, path) -> None:
        with self._lock:
            self._store.pop(str(path), None)


# Shared singleton
df_cache = DataFrameCache()
