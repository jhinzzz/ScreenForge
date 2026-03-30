import os

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import numpy as np
from numpy.linalg import norm
from pathlib import Path

# 重新引入 compute_instruction_hash，用于恢复精确匹配的 O(1) 极速查找
from common.logs import log
from .cache_stats import CacheStats
from .cache_hash import compute_ui_hash, compute_instruction_hash
from .cache_storage import load_cache, save_cache, cleanup_expired_entries
from .embedding_loader import EmbeddingModelLoader


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

        self._model_loader = EmbeddingModelLoader()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    def _get_model(self):
        """获取句子向量模型（委托给专门的加载器）"""
        return self._model_loader.load()

    def _get_embedding(self, text: str) -> list:
        return self._get_model().encode(text).tolist()

    def _cosine_similarity(self, vec1: list, vec2: list) -> float:
        v1, v2 = np.array(vec1), np.array(vec2)
        if norm(v1) == 0 or norm(v2) == 0:
            return 0.0
        return float(np.dot(v1, v2) / (norm(v1) * norm(v2)))

    # ==========================================
    # 混合检索引擎 (Exact Match + Semantic Fallback)
    # ==========================================
    def _hybrid_search(
        self,
        instruction: str,
        target_ui_hash: Optional[str],
        cache_type: str,
        threshold: float,
        exact_key: str,
    ) -> Optional[Dict]:
        if not self._enabled:
            return None
        self._stats.increment_query()

        try:
            cache_data = load_cache(self._cache_dir)
            cache_data = cleanup_expired_entries(cache_data, self._ttl_seconds)
            entries = cache_data.get("entries", {})
            if not entries:
                self._stats.increment_miss()
                return None

            # ----------------------------------------------------
            # O(1) 极速精确匹配
            # ----------------------------------------------------
            if exact_key in entries:
                matched_entry = entries[exact_key]
                log.info(f"🎯 [Exact Cache Hit] {cache_type} 命中")

                matched_entry["metadata"]["last_accessed"] = datetime.now(
                    timezone.utc
                ).isoformat()
                matched_entry["metadata"]["access_count"] = (
                    matched_entry["metadata"].get("access_count", 0) + 1
                )
                save_cache(self._cache_dir, cache_data)

                self._stats.increment_hit()
                return matched_entry.get("decision")

            # ----------------------------------------------------
            # O(N) 向量语义匹配 (泛化兜底)
            # ----------------------------------------------------
            current_vector = self._get_embedding(instruction)

            best_score = -1.0
            best_entry_key = None

            for key, entry in entries.items():
                if entry.get("type") != cache_type:
                    continue
                if target_ui_hash and entry.get("ui_hash") != target_ui_hash:
                    continue

                past_vector = entry.get("instruction_vector")
                if not past_vector:
                    continue

                score = self._cosine_similarity(current_vector, past_vector)
                if score > best_score:
                    best_score = score
                    best_entry_key = key

            if best_score >= threshold:
                matched_entry = entries[best_entry_key]
                past_inst = matched_entry.get("instruction")
                log.info(
                    f"🎯 [Semantic Cache Hit] {cache_type} 语义命中! 相似度: {best_score:.2%}"
                )
                log.info(f"💡 [System] 新指令: '{instruction}'")
                log.info(f"💡 [System] 旧指令: '{past_inst}'")

                matched_entry["metadata"]["last_accessed"] = datetime.now(
                    timezone.utc
                ).isoformat()
                matched_entry["metadata"]["access_count"] = (
                    matched_entry["metadata"].get("access_count", 0) + 1
                )
                save_cache(self._cache_dir, cache_data)

                self._stats.increment_hit()
                return matched_entry.get("decision")

            log.debug(
                f"🐌 [Cache Miss] 未精确命中，且最高语义相似度 {best_score:.2%} 未达阈值 {threshold:.2%}"
            )
            self._stats.increment_miss()
            return None

        except Exception as e:
            log.error(f"[Cache Error] 检索出错: {e}")
            return None

    def _set_hybrid(
        self,
        instruction: str,
        decision: Dict,
        ui_hash: Optional[str],
        cache_type: str,
        exact_key: str,
        llm_latency: float = 0.0,
    ) -> bool:
        if not self._enabled:
            return False
        try:
            cache_data = load_cache(self._cache_dir)
            entries = cache_data.setdefault("entries", {})

            # ====================================================
            # 写入前查重防膨胀机制 (Deduplication)
            # ====================================================
            current_vector = self._get_embedding(instruction)
            keys_to_delete = []

            for k, v in entries.items():
                if v.get("type") != cache_type:
                    continue

                is_same_decision = v.get("decision") == decision
                is_same_instruction = v.get("instruction") == instruction

                if cache_type == "L1-Action":
                    # 删掉旧的，保留最新的，避免同一个页面长出无数个相同逻辑的缓存节点
                    if (
                        is_same_instruction
                        and is_same_decision
                        and v.get("ui_hash") != ui_hash
                    ):
                        keys_to_delete.append(k)

                elif cache_type == "L2-SimpleQA":
                    # 当决策完全一致，且语义向量极其相似 (>0.98)
                    past_vector = v.get("instruction_vector")
                    if past_vector and is_same_decision:
                        sim = self._cosine_similarity(current_vector, past_vector)
                        if sim > 0.98:
                            # 仅更新旧条目的热度信息，安全返回
                            v["metadata"]["last_accessed"] = datetime.now(
                                timezone.utc
                            ).isoformat()
                            v["metadata"]["access_count"] = (
                                v["metadata"].get("access_count", 0) + 1
                            )
                            save_cache(self._cache_dir, cache_data)
                            return True

            # 清理检测到的过期废弃键
            for k in keys_to_delete:
                del entries[k]
            # ====================================================

            entry = {
                "type": cache_type,
                "instruction": instruction,
                "instruction_vector": current_vector,
                "decision": decision,
                "metadata": {
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "last_accessed": datetime.now(timezone.utc).isoformat(),
                    "access_count": 1,
                    "ttl_seconds": self._ttl_seconds,
                    "llm_latency": round(llm_latency, 2),
                },
            }
            if ui_hash is not None:
                entry["ui_hash"] = ui_hash

            entries[exact_key] = entry
            save_cache(self._cache_dir, cache_data)
            return True
        except Exception as e:
            log.error(f"[Cache Error] 写入出错: {e}")
            return False

    # ================= L1 混合页面缓存 (相同页面 + 相同/相似指令) =================
    def get(
        self, instruction: str, ui_json: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        ui_hash = compute_ui_hash(ui_json)
        inst_hash = compute_instruction_hash(instruction)
        exact_key = f"L1_{inst_hash}_{ui_hash}"
        return self._hybrid_search(instruction, ui_hash, "L1-Action", 0.90, exact_key)

    def set(
        self,
        instruction: str,
        ui_json: Dict[str, Any],
        decision: Dict[str, Any],
        llm_latency: float = 0.0,
    ) -> bool:
        ui_hash = compute_ui_hash(ui_json)
        inst_hash = compute_instruction_hash(instruction)
        exact_key = f"L1_{inst_hash}_{ui_hash}"
        return self._set_hybrid(
            instruction, decision, ui_hash, "L1-Action", exact_key, llm_latency
        )

    # ================= L2 混合纯问答缓存 (无视页面 + 相同/相似指令) =================
    def get_chat_simple(self, instruction: str) -> Optional[Dict[str, Any]]:
        inst_hash = compute_instruction_hash(instruction)
        exact_key = f"L2_{inst_hash}"
        return self._hybrid_search(instruction, None, "L2-SimpleQA", 0.88, exact_key)

    def set_chat_simple(
        self, instruction: str, decision: Dict[str, Any], llm_latency: float = 0.0
    ) -> bool:
        inst_hash = compute_instruction_hash(instruction)
        exact_key = f"L2_{inst_hash}"
        return self._set_hybrid(
            instruction, decision, None, "L2-SimpleQA", exact_key, llm_latency
        )

    # ================= 其他基础方法 =================
    def clear(self) -> bool:
        try:
            save_cache(self._cache_dir, {"version": "1.1", "entries": {}})
            return True
        except Exception:
            return False

    def get_stats(self) -> Dict[str, Any]:
        return self._stats.to_dict()
