import time
import os
import uiautomator2 as u2

import config.config as config
from common.ai import AIBrain
from common.executor import UIExecutor
from common.logs import log
from utils.utils_xml import compress_android_xml


def init_test_file():
    """初始化测试脚本"""
    # 确保 test_cases 文件夹存在
    os.makedirs(os.path.dirname(config.OUTPUT_SCRIPT_FILE), exist_ok=True)

    with open(config.OUTPUT_SCRIPT_FILE, "w", encoding="utf-8") as f:
        f.write("# -*- coding: utf-8 -*-\n")
        f.write("# 本脚本由 AI Agent 自动录制生成\n")
        f.write("import allure\n")
        f.write("import pytest\n\n")
        f.write("@allure.feature('核心业务流测试')\n")
        f.write("@allure.story('AI 自动录制场景')\n")
        # 参数 d 即调用 conftest.py 中的 fixture
        f.write("def test_auto_generated_case(d):\n")
        f.write('    """回放自动录制的 UI 步骤"""\n')


def launch_app(device: u2.Device, env_name="dev", system="android"):
    """启动指定环境的 App"""
    app = _get_app_config(env_name, system)
    device.app_start(app)

    log.info(f"✅ App 已启动: {app}")


def _get_app_config(env_name="dev", system="android"):
    """获取指定环境的 App 配置"""
    return config.APP_ENV_CONFIG.get(env_name, {})[system]


def main():
    log.info("=" * 50)
    log.info("🚀 Android AI 测试录制引擎 (Pytest+Allure 最佳实践)")
    log.info("=" * 50)

    try:
        device = u2.connect()
        if device is None:
            log.error("未连接到任何设备")
            raise Exception("未连接到任何设备")
        log.info("✅ 设备已连接")
        log.info(f"✅ 设备序列号: {device.serial}")
    except Exception as e:
        log.error(f"❌ 设备连接失败: {e}")
        return

    launch_app(device)

    init_test_file()
    log.info(f"✅ 测试脚本已创建: {config.OUTPUT_SCRIPT_FILE}")
    log.info("✅ 待操作 AI 填入测试用例内容")

    brain = AIBrain()
    executor = UIExecutor(device)

    with open(config.OUTPUT_SCRIPT_FILE, "a", encoding="utf-8") as file_obj:
        while True:
            cmd = input("\n👉 请输入自然语言指令 (输入 'q' 退出): ").strip()
            if not cmd:
                continue
            if cmd.lower() in ["exit", "q", "quit"]:
                log.info("🎉 录制结束！")
                log.info(f"已生成测试脚本，文件路径: {config.OUTPUT_SCRIPT_FILE}")
                log.info("请运行命令执行回放并查看报告：")
                log.info("1. pytest")
                log.info("2. allure serve ./report/allure-results")
                break

            time.sleep(1)  # 等待页面动画稳定

            log.info("[System] 抓取并压缩 XML 树")
            ui_json = compress_android_xml(device.dump_hierarchy())

            log.info("[System] AI 决策中")
            action_data = brain.get_action(cmd, ui_json)

            if action_data:
                executor.execute_and_record(action_data, file_obj)
            else:
                log.error("[System] ❌ 动作解析失败，请换一种描述。")


if __name__ == "__main__":
    main()
