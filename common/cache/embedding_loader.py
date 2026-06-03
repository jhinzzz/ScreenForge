from pathlib import Path
from typing import Any, Optional

from common.logs import log

# NOTE: `sentence_transformers` (and its torch/transformers stack, ~2GB) is an
# OPTIONAL dependency — installed via `pip install screenforge[ml]`, not the core
# requirements. It is imported lazily inside load(), NOT at module scope, so that
# importing common.cache / common.ai on a clean (core-only) install does not crash
# with ModuleNotFoundError. The semantic (vector) cache degrades gracefully when
# the package is absent; the exact-key (hash) cache keeps working.


class EmbeddingModelLoader:
    """负责句子向量模型的加载和缓存管理"""

    def __init__(
        self,
        model_name: str = "paraphrase-multilingual-MiniLM-L12-v2",
        hf_cache_dir: Optional[Path] = None,
        disable_ssl_verify: bool = True,
    ):
        self.model_name = model_name
        self.hf_cache_dir = hf_cache_dir or self._default_cache_dir(model_name)
        self.disable_ssl_verify = disable_ssl_verify
        self._model = None
        self._original_requests_init = None
        self._original_httpx_init = None

    @staticmethod
    def _default_cache_dir(model_name: str) -> Path:
        """计算 HuggingFace 模型的默认缓存目录"""
        return (
            Path.home()
            / ".cache"
            / "huggingface"
            / "hub"
            / f"models--sentence-transformers--{model_name}"
        )

    def _configure_network(self):
        """配置网络请求库（仅在模型加载期间生效，强制跳过 SSL）"""
        if not self.disable_ssl_verify:
            return

        import requests
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        # 保存对原函数的引用
        self._original_requests_init = requests.Session.__init__
        original_req_init = self._original_requests_init  # 通过局部变量闭包捕获

        def safe_session_init(sess_self, *args, **kwargs):
            # sess_self 是 requests.Session 实例
            original_req_init(sess_self, *args, **kwargs)
            sess_self.verify = False

        requests.Session.__init__ = safe_session_init

        try:
            import httpx

            # 保存对原函数的引用
            self._original_httpx_init = httpx.Client.__init__
            original_httpx_init = self._original_httpx_init  # 通过局部变量闭包捕获

            def safe_httpx_init(client_self, *args, **kwargs):
                # client_self 是 httpx.Client 实例
                kwargs["verify"] = False
                original_httpx_init(client_self, *args, **kwargs)

            httpx.Client.__init__ = safe_httpx_init
        except ImportError:
            self._original_httpx_init = None

    def _restore_network(self):
        """恢复网络请求库的原始配置，不污染全局环境"""
        if not self.disable_ssl_verify:
            return

        import requests

        if self._original_requests_init:
            requests.Session.__init__ = self._original_requests_init

        if self._original_httpx_init is not None:
            import httpx

            httpx.Client.__init__ = self._original_httpx_init

    def _cleanup_corrupted_cache(self) -> bool:
        """清理损坏的模型缓存"""
        if not self.hf_cache_dir.exists():
            return False

        import shutil

        log.warning("[System] Corrupted model cache detected, cleaning up...")
        shutil.rmtree(self.hf_cache_dir)
        log.info("[System] Corrupted cache cleaned")
        return True

    def _should_cleanup_cache(self, error_msg: str) -> bool:
        """判断是否需要清理缓存"""
        error_indicators = ["Can't load the model", "pytorch_model.bin", "safetensors"]
        return any(indicator in error_msg for indicator in error_indicators)

    def load(self) -> Optional[Any]:
        """加载模型（带缓存、代理兼容和错误处理机制）。

        ML 依赖缺失时返回 None（优雅降级，不抛异常），调用方据此跳过向量检索。
        """
        if self._model is not None:
            return self._model

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            log.warning(
                "[System] Semantic cache disabled — 'sentence_transformers' not "
                "installed. Install with: pip install screenforge[ml] (exact-key "
                "cache still works without it)."
            )
            return None

        log.info("[System] Initializing local semantic cache engine...")

        if not self.hf_cache_dir.exists():
            log.warning("[System] First run — downloading embedding model (~100MB)...")
        else:
            log.info("[System] Loading cached embedding model...")

        self._configure_network()

        try:
            try:
                self._model = SentenceTransformer(self.model_name)
            except Exception as e:
                if self._should_cleanup_cache(str(e)):
                    self._cleanup_corrupted_cache()
                    self._model = SentenceTransformer(self.model_name)
                else:
                    raise e

            log.info("[System] Semantic cache model loaded and ready")
            return self._model
        finally:
            self._restore_network()
