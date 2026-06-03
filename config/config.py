import os
from pathlib import Path

from common.logs import log
from config.env_loader import resolve_dotenv_path, safe_load_dotenv

# ==========================================
# 1. 基础路径与 .env 自动加载 (工程化核心)
# ==========================================
# 动态获取项目根目录 (config.py 的上一级目录)
BASE_DIR = Path(__file__).resolve().parent.parent

# 尝试寻找并加载根目录或上层主仓库中的 .env/.ENV 文件到系统环境变量中
# override=False 表示如果宿主系统已经配置了该变量(如在 CI/CD 流水线中)，则以系统优先
env_path = resolve_dotenv_path(BASE_DIR)
safe_load_dotenv(dotenv_path=env_path, override=False)

# ==========================================
# 2. 文本大模型配置 (用于处理纯 XML 树，高频、廉价、快速)
# ==========================================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o")

# ==========================================
# 3. 多模态视觉大模型配置 (用于处理屏幕截图，低频、复杂场景辅助)
# ==========================================
# 默认 fallback 到文本模型的配置，实现优雅降级；若配置了则实现异构解耦
VISION_API_KEY = os.getenv("VISION_API_KEY", OPENAI_API_KEY)
VISION_BASE_URL = os.getenv("VISION_BASE_URL", OPENAI_BASE_URL)
VISION_MODEL_NAME = os.getenv("VISION_MODEL_NAME", MODEL_NAME)

# ==========================================
# 4. 自动化自愈配置 (Self-Healing)
# ==========================================
# 开启 AI 自动修复失败用例功能
AUTO_HEAL_ENABLED = str(os.getenv("AUTO_HEAL_ENABLED", "True")).lower() in ('true', '1', 'yes')
# 连续失败多少次后触发自愈
AUTO_HEAL_TRIGGER_THRESHOLD = int(os.getenv("AUTO_HEAL_TRIGGER_THRESHOLD", 2))
# 自愈置信度阈值 — 低于此值的修复方案将被丢弃
AUTO_HEAL_MIN_CONFIDENCE = float(os.getenv("AUTO_HEAL_MIN_CONFIDENCE", 0.7))

# ==========================================
# 5. 自动化测试框架配置
# ==========================================
# 使用绝对路径，彻底杜绝不同命令路径下生成文件夹位置错乱的问题
OUTPUT_SCRIPT_FILE = str(BASE_DIR / "test_cases" / "test_auto_generated.py")

# 全局隐式等待时间，强转为 float 确保安全
DEFAULT_TIMEOUT = float(os.getenv("DEFAULT_TIMEOUT", 30.0))

# ==========================================
# 6. App 环境配置
# ==========================================
APP_ENV_CONFIG = {
    "dev": {
        "android": "",
        "ios": "",
        "web": "",
    },
}

# ==========================================
# 7. 本地语义缓存配置
# ==========================================
# 强转布尔值，兼容 .env 中的 True/true/1/yes
CACHE_ENABLED = str(os.getenv("CACHE_ENABLED", "True")).lower() in ('true', '1', 't', 'yes')
CACHE_DIR = str(BASE_DIR / '.cache')
CACHE_TTL_DAYS = int(os.getenv("CACHE_TTL_DAYS", 7))
CACHE_MAX_SIZE_MB = int(os.getenv("CACHE_MAX_SIZE_MB", 100))
CACHE_COMPRESSION = str(os.getenv("CACHE_COMPRESSION", "False")).lower() in ('true', '1', 't', 'yes')

CACHE_SIMILARITY_THRESHOLD = float(os.getenv("CACHE_SIMILARITY_THRESHOLD", "0.90"))
CACHE_EXACT_MATCH_THRESHOLD = float(os.getenv("CACHE_EXACT_MATCH_THRESHOLD", "0.98"))


# ==========================================
# 8. Web CDP 连接配置
# ==========================================
WEB_CDP_URL = os.getenv("WEB_CDP_URL", "http://localhost:9222")

# ==========================================
# 8a. Android 设备连接配置
# ==========================================
ANDROID_SERIAL = os.getenv("ANDROID_SERIAL", "")
ANDROID_CONNECT_TIMEOUT = float(os.getenv("ANDROID_CONNECT_TIMEOUT", "10.0"))

# ==========================================
# 8b. iOS 设备连接配置
# ==========================================
WDA_URL = os.getenv("WDA_URL", "http://localhost:8100")
IOS_DEVICE_UDID = os.getenv("IOS_DEVICE_UDID", "")

# ==========================================
# 9. Agent 运行产物目录
# ==========================================
RUN_REPORT_BASE_DIR = BASE_DIR / "report" / "runs"

# ==========================================
# 10. 跨运行测试记忆目录
# ==========================================
CASE_MEMORY_PATH = Path(os.getenv("CASE_MEMORY_PATH", str(BASE_DIR / "memory" / "case_memory.json")))

# ==========================================
# 11. Pytest 真机回放测试控制
# ==========================================
TEST_PLATFORM = os.getenv("TEST_PLATFORM", "android").lower()
RUN_LIVE_PLATFORM_TESTS = str(os.getenv("RUN_LIVE_PLATFORM_TESTS", "False")).lower() in (
    "true",
    "1",
    "t",
    "yes",
)


def validate_config() -> bool:
    """Validate required configuration. Returns False and logs errors on failure."""
    errors: list[tuple[str, str, str]] = []  # (code, what, fix)

    if not OPENAI_API_KEY:
        errors.append((
            "E001",
            "OPENAI_API_KEY is not set.",
            "Fix: export OPENAI_API_KEY=sk-... or add it to your .env file",
        ))
    if DEFAULT_TIMEOUT <= 0:
        errors.append((
            "E002",
            f"DEFAULT_TIMEOUT must be > 0 (current: {DEFAULT_TIMEOUT}).",
            "Fix: export DEFAULT_TIMEOUT=30",
        ))
    if not (0 <= CACHE_SIMILARITY_THRESHOLD <= 1):
        errors.append((
            "E003",
            f"CACHE_SIMILARITY_THRESHOLD must be 0-1 (current: {CACHE_SIMILARITY_THRESHOLD}).",
            "Fix: export CACHE_SIMILARITY_THRESHOLD=0.90",
        ))
    if not (0 <= CACHE_EXACT_MATCH_THRESHOLD <= 1):
        errors.append((
            "E004",
            f"CACHE_EXACT_MATCH_THRESHOLD must be 0-1 (current: {CACHE_EXACT_MATCH_THRESHOLD}).",
            "Fix: export CACHE_EXACT_MATCH_THRESHOLD=0.98",
        ))
    if not WEB_CDP_URL.startswith(("http://", "https://")):
        errors.append((
            "E005",
            f"WEB_CDP_URL must start with http:// or https:// (current: {WEB_CDP_URL}).",
            "Fix: export WEB_CDP_URL=http://localhost:9222",
        ))
    if not (0 <= AUTO_HEAL_MIN_CONFIDENCE <= 1):
        errors.append((
            "E006",
            f"AUTO_HEAL_MIN_CONFIDENCE must be 0-1 (current: {AUTO_HEAL_MIN_CONFIDENCE}).",
            "Fix: export AUTO_HEAL_MIN_CONFIDENCE=0.7",
        ))
    if AUTO_HEAL_TRIGGER_THRESHOLD < 1:
        errors.append((
            "E007",
            f"AUTO_HEAL_TRIGGER_THRESHOLD must be >= 1 (current: {AUTO_HEAL_TRIGGER_THRESHOLD}).",
            "Fix: export AUTO_HEAL_TRIGGER_THRESHOLD=2",
        ))

    if errors:
        for code, what, fix in errors:
            log.error(f"[{code}] {what} {fix}")
        return False
    return True
