import os

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np
from numpy.linalg import norm

from common.logs import log
from config.config import CACHE_EXACT_MATCH_THRESHOLD, CACHE_SIMILARITY_THRESHOLD

from .cache_hash import compute_instruction_hash, compute_ui_hash
from .cache_stats import CacheStats
from .cache_storage import cleanup_expired_entries, load_cache, save_cache
from .embedding_loader import EmbeddingModelLoader


class CacheManager:
    def __init__(
        self,
        cache_dir: str = ".cache",
        enabled: bool = False,
        ttl_days: int = 365,
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
        return self._model_loader.load()

    def _get_embedding(self, text: str) -> Optional[list]:
        # Returns None when the ML stack (sentence_transformers) is unavailable,
        # so callers can fall back to exact-key-only behavior instead of crashing.
        model = self._get_model()
        if model is None:
            return None
        return model.encode(text).tolist()

    def _cosine_similarity(self, vec1: list, vec2: list) -> float:
        v1, v2 = np.array(vec1), np.array(vec2)
        norm1, norm2 = norm(v1), norm(v2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(np.dot(v1, v2) / (norm1 * norm2))

    def _cosine_similarity_batch(
        self, query_vec: list, candidate_vecs: List[list]
    ) -> List[tuple]:
        if not candidate_vecs:
            return []
        q = np.array(query_vec)
        q_norm = norm(q)
        if q_norm == 0:
            return []

        candidates = np.stack(candidate_vecs)
        candidate_norms = norm(candidates, axis=1)
        scores = np.zeros(len(candidate_vecs))

        valid_indices = candidate_norms > 0
        if np.any(valid_indices):
            scores[valid_indices] = np.dot(candidates[valid_indices], q) / (
                candidate_norms[valid_indices] * q_norm
            )

        return list(enumerate(scores.tolist()))

    def _hybrid_search(
        self,
        instruction: str,
        target_ui_hash: Optional[str],
        cache_type: str,
        platform: str,
        threshold: float,
        exact_key: str,
    ) -> Optional[Dict]:
        if not self._enabled:
            return None

        try:
            cache_data = load_cache(self._cache_dir)
            cache_data = cleanup_expired_entries(cache_data, self._ttl_seconds)
            entries = cache_data.get("entries", {})
            if not entries:
                self._stats.increment_miss()
                return None

            if exact_key in entries:
                matched_entry = entries[exact_key]
                if matched_entry.get("platform") == platform:
                    saved_time = matched_entry.get("metadata", {}).get("llm_latency", 0.0)
                    log.info(f"[Exact Cache Hit] {cache_type} matched ({platform})")
                    if saved_time > 0:
                        log.info(f"[Cache] Saved {saved_time:.2f}s of LLM inference time")
                    matched_entry["metadata"]["last_accessed"] = datetime.now(timezone.utc).isoformat()
                    matched_entry["metadata"]["access_count"] = matched_entry["metadata"].get("access_count", 0) + 1
                    save_cache(self._cache_dir, cache_data)
                    self._stats.increment_hit()
                    return matched_entry.get("decision")

            current_vector = self._get_embedding(instruction)
            if current_vector is None:
                # ML stack unavailable: exact-key already missed above, and we
                # can't do semantic similarity without embeddings. Treat as miss.
                self._stats.increment_miss()
                return None
            candidate_entries = []
            candidate_vectors = []
            for key, entry in entries.items():
                if entry.get("type") != cache_type:
                    continue
                if entry.get("platform") != platform:
                    continue
                if target_ui_hash and entry.get("ui_hash") != target_ui_hash:
                    continue
                past_vector = entry.get("instruction_vector")
                if not past_vector:
                    continue
                candidate_entries.append(entry)
                candidate_vectors.append(past_vector)
            if not candidate_vectors:
                log.debug("[Cache Miss] No candidate vectors to compare")
                self._stats.increment_miss()
                return None
            scores = self._cosine_similarity_batch(current_vector, candidate_vectors)
            if not scores:
                log.debug("[Cache Miss] No similarity scores computed")
                self._stats.increment_miss()
                return None
            best_idx, best_score = max(scores, key=lambda s: s[1])
            if best_score >= threshold:
                matched_entry = candidate_entries[best_idx]
                past_inst = matched_entry.get("instruction")
                saved_time = matched_entry.get("metadata", {}).get("llm_latency", 0.0)
                log.info(f"[Semantic Cache Hit] {cache_type} matched, similarity: {best_score:.2%} ({platform})")
                log.info(f"[Cache] Query: '{instruction}' | Matched: '{past_inst}'")
                if saved_time > 0:
                    log.info(f"[Cache] Saved {saved_time:.2f}s of LLM inference time")
                matched_entry["metadata"]["last_accessed"] = datetime.now(timezone.utc).isoformat()
                matched_entry["metadata"]["access_count"] = matched_entry["metadata"].get("access_count", 0) + 1
                save_cache(self._cache_dir, cache_data)
                self._stats.increment_hit()
                return matched_entry.get("decision")
            log.debug(f"[Cache Miss] Best similarity {best_score:.2%} below threshold {threshold:.2%}")
            self._stats.increment_miss()
            return None
        except Exception as e:
            log.error(f"[Cache Error] Retrieval failed: {e}")
            return None

    def _set_hybrid(
        self,
        instruction: str,
        decision: Dict,
        ui_hash: Optional[str],
        cache_type: str,
        platform: str,
        exact_key: str,
        llm_latency: float = 0.0,
    ) -> bool:
        if not self._enabled:
            return False
        try:
            cache_data = load_cache(self._cache_dir)
            entries = cache_data.setdefault("entries", {})
            current_vector = self._get_embedding(instruction)
            keys_to_delete = []
            for k, v in entries.items():
                if v.get("type") != cache_type:
                    continue
                if v.get("platform") != platform:
                    continue
                is_same_decision = v.get("decision") == decision
                is_same_instruction = v.get("instruction") == instruction
                if cache_type == "L1-Action":
                    if is_same_instruction and is_same_decision and v.get("ui_hash") != ui_hash:
                        keys_to_delete.append(k)
                elif cache_type == "L2-SimpleQA":
                    past_vector = v.get("instruction_vector")
                    if current_vector is not None and past_vector and is_same_decision:
                        sim = self._cosine_similarity(current_vector, past_vector)
                        if sim > CACHE_EXACT_MATCH_THRESHOLD:
                            v["metadata"]["last_accessed"] = datetime.now(timezone.utc).isoformat()
                            v["metadata"]["access_count"] = v["metadata"].get("access_count", 0) + 1
                            save_cache(self._cache_dir, cache_data)
                            return True
            for k in keys_to_delete:
                del entries[k]
            entry = {
                "type": cache_type,
                "platform": platform,
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
            log.error(f"[Cache Error] Write failed: {e}")
            return False

    def get(self, instruction: str, ui_json: Dict[str, Any], platform: str) -> Optional[Dict[str, Any]]:
        try:
            ui_hash = compute_ui_hash(ui_json)
            inst_hash = compute_instruction_hash(instruction)
            exact_key = f"L1_{platform}_{inst_hash}_{ui_hash}"
            return self._hybrid_search(
                instruction, ui_hash, "L1-Action", platform, CACHE_SIMILARITY_THRESHOLD, exact_key
            )
        except Exception as e:
            log.error(f"[Cache Error] get() failed: {e}")
            return None

    def set(
        self,
        instruction: str,
        ui_json: Dict[str, Any],
        decision: Dict[str, Any],
        platform: str,
        llm_latency: float = 0.0,
    ) -> bool:
        try:
            ui_hash = compute_ui_hash(ui_json)
            inst_hash = compute_instruction_hash(instruction)
            exact_key = f"L1_{platform}_{inst_hash}_{ui_hash}"
            return self._set_hybrid(
                instruction, decision, ui_hash, "L1-Action", platform, exact_key, llm_latency
            )
        except Exception as e:
            log.error(f"[Cache Error] set() failed: {e}")
            return False

    def get_chat_simple(self, instruction: str, platform: str) -> Optional[Dict[str, Any]]:
        try:
            inst_hash = compute_instruction_hash(instruction)
            exact_key = f"L2_{platform}_{inst_hash}"
            return self._hybrid_search(
                instruction, None, "L2-SimpleQA", platform, 0.88, exact_key
            )
        except Exception as e:
            log.error(f"[Cache Error] get_chat_simple() failed: {e}")
            return None

    def set_chat_simple(
        self,
        instruction: str,
        decision: Dict[str, Any],
        platform: str,
        llm_latency: float = 0.0,
    ) -> bool:
        try:
            inst_hash = compute_instruction_hash(instruction)
            exact_key = f"L2_{platform}_{inst_hash}"
            return self._set_hybrid(
                instruction, decision, None, "L2-SimpleQA", platform, exact_key, llm_latency
            )
        except Exception as e:
            log.error(f"[Cache Error] set_chat_simple() failed: {e}")
            return False

    def clear(self) -> bool:
        try:
            save_cache(self._cache_dir, {"version": "1.2", "entries": {}})
            return True
        except Exception as e:
            log.error(f"[Cache Error] clear() failed: {e}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        try:
            return self._stats.to_dict()
        except Exception as e:
            log.error(f"[Cache Error] get_stats() failed: {e}")
            return {}
