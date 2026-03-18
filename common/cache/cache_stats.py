import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional
from filelock import FileLock

class CacheStats:
    def __init__(self, cache_dir: str = ".cache"):
        self._cache_dir = cache_dir
        self._total_queries = 0
        self._cache_hits = 0
        self._cache_misses = 0
        self._total_api_calls_saved = 0
        self._first_cache_date = None
        self._last_cache_date = None
        self._load_stats()

    @property
    def total_queries(self) -> int:
        return self._total_queries

    @property
    def cache_hits(self) -> int:
        return self._cache_hits

    @property
    def cache_misses(self) -> int:
        return self._cache_misses

    @property
    def hit_rate(self) -> float:
        if self._total_queries == 0:
            return 0.0
        return self._cache_hits / self._total_queries

    @property
    def total_api_calls_saved(self) -> int:
        return self._total_api_calls_saved

    @property
    def first_cache_date(self) -> Optional[str]:
        return self._first_cache_date

    @property
    def last_cache_date(self) -> Optional[str]:
        return self._last_cache_date

    def increment_query(self) -> None:
        self._total_queries += 1
        self._update_last_cache_date()
        self._save_stats()

    def increment_hit(self) -> None:
        self._total_queries += 1
        self._cache_hits += 1
        self._total_api_calls_saved += 1
        self._update_last_cache_date()
        self._save_stats()

    def increment_miss(self) -> None:
        self._total_queries += 1
        self._cache_misses += 1
        self._update_last_cache_date()
        self._save_stats()

    def _update_first_cache_date(self) -> None:
        if not self._first_cache_date:
            self._first_cache_date = datetime.now(timezone.utc).isoformat()

    def _update_last_cache_date(self) -> None:
        self._last_cache_date = datetime.now(timezone.utc).isoformat()
        self._update_first_cache_date()

    def _load_stats(self) -> None:
        stats_path = Path(self._cache_dir) / "cache_stats.json"
        os.makedirs(self._cache_dir, exist_ok=True)
        lock = FileLock(f"{stats_path}.lock")

        try:
            with lock:
                if not stats_path.exists():
                    return
                with open(stats_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            self._total_queries = data.get("total_queries", 0)
            self._cache_hits = data.get("cache_hits", 0)
            self._cache_misses = data.get("cache_misses", 0)
            self._total_api_calls_saved = data.get("total_api_calls_saved", 0)
            self._first_cache_date = data.get("first_cache_date")
            self._last_cache_date = data.get("last_cache_date")
        except (json.JSONDecodeError, IOError):
            pass

    def _save_stats(self) -> None:
        stats_path = Path(self._cache_dir) / "cache_stats.json"
        temp_path = stats_path.with_suffix(".tmp")
        os.makedirs(self._cache_dir, exist_ok=True)
        lock = FileLock(f"{stats_path}.lock")

        data = {
            "total_queries": self._total_queries,
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate": (self._cache_hits / self._total_queries) if self._total_queries > 0 else 0.0,
            "total_api_calls_saved": self._total_api_calls_saved,
            "first_cache_date": self._first_cache_date,
            "last_cache_date": self._last_cache_date
        }
        try:
            with lock:
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temp_path, stats_path)
        except IOError:
            if temp_path.exists():
                temp_path.unlink()
            raise

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_queries": self._total_queries,
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate": (self._cache_hits / self._total_queries) if self._total_queries > 0 else 0.0,
            "total_api_calls_saved": self._total_api_calls_saved,
            "first_cache_date": self._first_cache_date,
            "last_cache_date": self._last_cache_date
        }
