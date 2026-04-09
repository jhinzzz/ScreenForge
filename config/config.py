import os
from pathlib import Path

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
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
MODEL_NAME = os.getenv("MODEL_NAME", "doubao-seed-2-0-lite-260215")

# ==========================================
# 3. 多模态视觉大模型配置 (用于处理屏幕截图，低频、复杂场景辅助)
# ==========================================
# 默认 fallback 到文本模型的配置，实现优雅降级；若配置了则实现异构解耦
VISION_API_KEY = os.getenv("VISION_API_KEY", OPENAI_API_KEY)
VISION_BASE_URL = os.getenv("VISION_BASE_URL", OPENAI_BASE_URL)
VISION_MODEL_NAME = os.getenv("VISION_MODEL_NAME", "doubao-seed-2-0-lite-260215")

# ==========================================
# 4. 自动化自愈配置 (Self-Healing)
# ==========================================
# 开启 AI 自动修复失败用例功能
AUTO_HEAL_ENABLED = str(os.getenv("AUTO_HEAL_ENABLED", "True")).lower() in ('true', '1', 'yes')
# 连续失败多少次后触发自愈
AUTO_HEAL_TRIGGER_THRESHOLD = int(os.getenv("AUTO_HEAL_TRIGGER_THRESHOLD", 2))

# ==========================================
# 5. 自动化测试框架配置
# ==========================================
# 使用绝对路径，彻底杜绝不同命令路径下生成文件夹位置错乱的问题
OUTPUT_SCRIPT_FILE = str(BASE_DIR / "test_cases" / "test_auto_generated.py")

# 全局隐式等待时间，强转为 float 确保安全
DEFAULT_TIMEOUT = float(os.getenv("DEFAULT_TIMEOUT", 5.0))

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
# Web CDP 连接地址（用于连接已运行的系统 Chrome）
WEB_CDP_URL = os.getenv("WEB_CDP_URL", "http://localhost:9222")

# ==========================================
# 9. Agent 运行产物目录
# ==========================================
RUN_REPORT_BASE_DIR = BASE_DIR / "report" / "runs"

# ==========================================
# 10. Pytest 真机回放测试控制
# ==========================================
TEST_PLATFORM = os.getenv("TEST_PLATFORM", "android").lower()
RUN_LIVE_PLATFORM_TESTS = str(os.getenv("RUN_LIVE_PLATFORM_TESTS", "False")).lower() in (
    "true",
    "1",
    "t",
    "yes",
)


def validate_config() -> bool:
    errors = []
    if not OPENAI_API_KEY:
        errors.append("OPENAI_API_KEY 未配置")
    if DEFAULT_TIMEOUT <= 0:
        errors.append(f"DEFAULT_TIMEOUT 必须大于 0，当前值: {DEFAULT_TIMEOUT}")
    if CACHE_SIMILARITY_THRESHOLD < 0 or CACHE_SIMILARITY_THRESHOLD > 1:
        errors.append(f"CACHE_SIMILARITY_THRESHOLD 必须在 0-1 之间，当前值: {CACHE_SIMILARITY_THRESHOLD}")
    if CACHE_EXACT_MATCH_THRESHOLD < 0 or CACHE_EXACT_MATCH_THRESHOLD > 1:
        errors.append(f"CACHE_EXACT_MATCH_THRESHOLD 必须在 0-1 之间，当前值: {CACHE_EXACT_MATCH_THRESHOLD}")
    if not WEB_CDP_URL.startswith(("http://", "https://")):
        errors.append(f"WEB_CDP_URL 必须以 http:// 或 https:// 开头，当前值: {WEB_CDP_URL}")
    if errors:
        for err in errors:
            print(f"[Config Error] {err}")
        return False
    return True
