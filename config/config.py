import os

# --- LLM 大模型配置 ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "")
MODEL_NAME = os.getenv("MODEL_NAME", "")

# --- 自动化测试框架配置 ---
# 录制生成的用例存放路径（统一放在 test_cases 下以匹配 pytest 规则）
OUTPUT_SCRIPT_FILE = os.path.join("test_cases", "test_auto_generated.py")

# 全局隐式等待时间（秒），缓解页面异步加载导致的找不到元素问题
DEFAULT_TIMEOUT = 5.0

# --- App 环境配置 ---
APP_ENV_CONFIG = {
    "dev": {
        "android": "",
        "ios": "",
        "web": "",
    }
}
