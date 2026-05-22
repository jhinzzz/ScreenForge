from pathlib import Path
from typing import Optional

from sentence_transformers import SentenceTransformer

from common.logs import log


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

        log.warning("⚠️ [System] 检测到模型缓存损坏，正在清理...")
        shutil.rmtree(self.hf_cache_dir)
        log.info("🧹 [System] 已清理损坏的缓存")
        return True

    def _should_cleanup_cache(self, error_msg: str) -> bool:
        """判断是否需要清理缓存"""
        error_indicators = ["Can't load the model", "pytorch_model.bin", "safetensors"]
        return any(indicator in error_msg for indicator in error_indicators)

    def load(self) -> SentenceTransformer:
        """加载模型（带缓存、代理兼容和错误处理机制）"""
        if self._model is not None:
            return self._model

        log.info("⏳ [System] 正在初始化本地语义缓存引擎...")

        if not self.hf_cache_dir.exists():
            log.warning("⏳ [System] 首次运行将自动下载模型 (约 100MB)。")
            log.warning(
                "⏳ [System] 正在通过国内镜像源加速下载，请耐心等待 1~3 分钟..."
            )
        else:
            log.info("✅ [System] 检测到本地已有模型缓存，正在极速加载中...")

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

            log.info("✅ [System] 语义缓存模型加载完毕，准备就绪！")
            return self._model
        finally:
            self._restore_network()
