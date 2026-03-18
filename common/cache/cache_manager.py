from datetime import datetime, timezone
from typing import Any, Dict, Optional
from .cache_hash import compute_cache_key, compute_chat_cache_key
from .cache_storage import load_cache, save_cache, cleanup_expired_entries
from .cache_stats import CacheStats
from common.logs import log


class CacheManager:
    def __init__(
        self,
        cache_dir: str = ".cache",
        enabled: bool = False,
        ttl_days: int = 7,
        max_size_mb: int = 100,
    ):
        self._cache_dir = cache_dir
        self._enabled = enabled
        self._ttl_seconds = ttl_days * 24 * 60 * 60
        self._stats = CacheStats(cache_dir)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    def _get_internal(self, cache_key: str, cache_type: str) -> Optional[Dict[str, Any]]:
        if not self._enabled:
            return None

        log.debug(f"[Cache {cache_type}] 查询 - Key: {cache_key[:32]}...")
        self._stats.increment_query()

        try:
            cache_data = load_cache(self._cache_dir)
            cache_data = cleanup_expired_entries(cache_data, self._ttl_seconds)

            entry = cache_data.get("entries", {}).get(cache_key)
            if entry:
                log.info(f"🎯 [Cache {cache_type} Hit] 缓存命中！")
                entry["metadata"]["last_accessed"] = datetime.now(
                    timezone.utc
                ).isoformat()
                entry["metadata"]["access_count"] = (
                    entry["metadata"].get("access_count", 0) + 1
                )
                save_cache(self._cache_dir, cache_data)

                self._stats.increment_hit()
                return entry.get("decision")

            self._stats.increment_miss()
            return None
        except Exception as e:
            log.error(f"[Cache {cache_type} Error] 查询出错: {e}")
            return None

    def _set_internal(
        self,
        cache_key: str,
        instruction: str,
        decision: Dict[str, Any],
        cache_type: str,
        ttl_seconds: int,
    ) -> bool:
        if not self._enabled:
            return False

        try:
            cache_data = load_cache(self._cache_dir)
            cache_data = cleanup_expired_entries(cache_data, self._ttl_seconds)

            cache_data.setdefault("entries", {})[cache_key] = {
                "type": cache_type,
                "instruction": instruction,
                "decision": decision,
                "metadata": {
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "last_accessed": datetime.now(timezone.utc).isoformat(),
                    "access_count": 1,
                    "ttl_seconds": ttl_seconds,
                },
            }
            save_cache(self._cache_dir, cache_data)
            # ✅ 修复封装漏洞：不再直接调用私有方法
            self._stats.increment_query()  # 记录内部状态变化
            return True
        except Exception as e:
            log.error(f"[Cache {cache_type} Error] 写入出错: {e}")
            return False

    # 对外暴露的业务接口
    def get(
        self, instruction: str, ui_json: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        cache_key = compute_cache_key(instruction, ui_json)
        return self._get_internal(cache_key, "L1-Action")

    def set(
        self, instruction: str, ui_json: Dict[str, Any], decision: Dict[str, Any]
    ) -> bool:
        cache_key = compute_cache_key(instruction, ui_json)
        return self._set_internal(
            cache_key, instruction, decision, "L1-Action", self._ttl_seconds
        )

    def get_chat(self, instruction: str, raw_xml: str) -> Optional[Dict[str, Any]]:
        cache_key = compute_chat_cache_key(instruction, raw_xml)
        return self._get_internal(cache_key, "L2-QA")

    def set_chat(
        self,
        instruction: str,
        raw_xml: str,
        decision: Dict[str, Any],
        ttl_seconds: int = 300,
    ) -> bool:
        cache_key = compute_chat_cache_key(instruction, raw_xml)
        return self._set_internal(
            cache_key, instruction, decision, "L2-QA", ttl_seconds
        )

    def clear(self) -> bool:
        try:
            save_cache(self._cache_dir, {"version": "1.1", "entries": {}})
            return True
        except Exception:
            return False

    def get_stats(self) -> Dict[str, Any]:
        return self._stats.to_dict()
