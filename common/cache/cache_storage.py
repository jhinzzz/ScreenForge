import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from filelock import FileLock


def get_cache_filename() -> str:
    # 统一使用 UTC 时间，避免时区/夏令时带来的 Bug
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"ai_decisions_{today}.json"


def _get_lock_path(cache_path: Path) -> str:
    return f"{cache_path}.lock"


def load_cache(cache_dir: str) -> Dict[str, Any]:
    cache_path = Path(cache_dir) / get_cache_filename()
    if not cache_path.exists():
        return {"version": "1.1", "entries": {}}

    lock = FileLock(_get_lock_path(cache_path))
    try:
        with lock:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        return data if "entries" in data else {"version": "1.1", "entries": {}}
    except (json.JSONDecodeError, IOError):
        return {"version": "1.1", "entries": {}}


def save_cache(cache_dir: str, data: Dict[str, Any]) -> None:
    cache_path = Path(cache_dir) / get_cache_filename()
    temp_path = cache_path.with_suffix(".tmp")
    os.makedirs(cache_dir, exist_ok=True)

    lock = FileLock(_get_lock_path(cache_path))
    try:
        with lock:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, cache_path)
    except IOError:
        if temp_path.exists():
            temp_path.unlink()
        raise


def cleanup_expired_entries(
    data: Dict[str, Any], default_ttl_seconds: float
) -> Dict[str, Any]:
    if "entries" not in data:
        return data

    now = time.time()
    cleaned_entries = {}

    for key, entry in data["entries"].items():
        metadata = entry.get("metadata", {})
        created_at = metadata.get("created_at")
        if not created_at:
            continue

        try:
            # 标准化 UTC 时间解析
            created_time = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            entry_ttl = metadata.get("ttl_seconds", default_ttl_seconds)

            if now - created_time.timestamp() <= entry_ttl:
                cleaned_entries[key] = entry
        except ValueError:
            continue

    return {"version": data.get("version", "1.1"), "entries": cleaned_entries}
