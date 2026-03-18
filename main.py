import os
import time

import uiautomator2 as u2

from common.ai import AIBrain
from common.logs import log
from common.executor import UIExecutor
from common.history_manager import StepHistoryManager
import config.config as config
from utils.utils_xml import compress_android_xml


def get_initial_header() -> list:
    """获取测试脚本的初始头部内容"""
    return [
        "# -*- coding: utf-8 -*-\n",
        "# 本脚本由 AI Agent 自动录制生成\n",
        "import allure\n",
        "import pytest\n\n",
        "from common.logs import log\n\n",
        "@allure.feature('核心业务流测试')\n",
        "@allure.story('AI 自动录制场景')\n",
        # 参数 d 即调用 conftest.py 中的 fixture
        "def test_auto_generated_case(d):\n",
        '    """回放自动录制的 UI 步骤"""\n'
    ]


def save_to_disk(file_path: str, content: list) -> None:
    """安全的原子化文件写入，防止因断电等原因导致测试脚本被清空"""
    log.debug(f"[SaveToDisk] 脚本保存至 {file_path}, 内容长度: {len(content)}")
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    # 先写入临时文件
    temp_path = file_path + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        f.writelines(content)
    # 原子替换，确保安全落地
    os.replace(temp_path, file_path)
    log.debug("[SaveToDisk] 文件原子保存成功")


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
    log.info("🚀 AI 测试录制引擎")
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

    # 初始化历史管理器，传入初始头部内容
    initial_header = get_initial_header()
    history_manager = StepHistoryManager(initial_content=initial_header)

    # 保存初始文件到磁盘
    save_to_disk(config.OUTPUT_SCRIPT_FILE, initial_header)
    log.info(f"✅ 测试脚本已创建: {config.OUTPUT_SCRIPT_FILE}")
    log.info("✅ 待操作 AI 填入测试用例内容")

    brain = AIBrain()
    executor = UIExecutor(device)

    while True:
        history_count = history_manager.get_history_count()
        cache_status = "✅" if brain.cache_manager.enabled else "❌"
        prompt = f"\n👉 请输入自然语言指令 (输入 'q' 退出, 'u' 撤销) [已录制 {history_count} 步] [缓存: {cache_status}]: "
        cmd = input(prompt).strip()

        if not cmd:
            continue

        if cmd.lower() in ["exit", "q", "quit"]:
            log.info("🎉 录制结束！")
            log.info(f"已生成测试脚本，文件路径: {config.OUTPUT_SCRIPT_FILE}")
            log.info("请运行命令执行回放并查看报告：")
            log.info("1. pytest")
            log.info("2. allure serve ./report/allure-results")
            break

        if cmd.lower() == "cache":
            stats = brain.cache_manager.get_stats()
            log.info(f"\n{'='*60}")
            log.info("📊 缓存统计信息")
            log.info(f"{'='*60}")
            log.info(f"缓存状态: {'✅ 已启用' if brain.cache_manager.enabled else '❌ 已禁用'}")
            log.info(f"总查询次数: {stats['total_queries']}")
            log.info(f"缓存命中: {stats['cache_hits']}")
            log.info(f"缓存未命中: {stats['cache_misses']}")
            log.info(f"命中率: {stats['hit_rate']:.2%}")
            log.info(f"节省的 API 调用: {stats['total_api_calls_saved']}")
            if stats.get('first_cache_date'):
                log.info(f"首次缓存时间: {stats['first_cache_date']}")
            if stats.get('last_cache_date'):
                log.info(f"最后缓存时间: {stats['last_cache_date']}")
            log.info(f"{'='*60}")
            continue

        if cmd.lower() == "cache-on":
            brain.cache_manager.enabled = True
            log.info("✅ 缓存已启用")
            continue

        if cmd.lower() == "cache-off":
            brain.cache_manager.enabled = False
            log.info("❌ 缓存已禁用")
            continue

        if cmd.lower() == "cache-clear":
            if brain.cache_manager.clear():
                log.info("🗑️ 缓存已清空")
            else:
                log.error("❌ 清空缓存失败")
            continue

        # 回滚操作
        if cmd.lower() in ["u", "undo"]:
            last_step = history_manager.get_last_step()
            history_count_before = history_manager.get_history_count()

            if not last_step:
                log.warning("⚠️ 无可撤销的步骤")
                continue

            # 显示最后一步的信息并请求确认
            log.info(f"\n{'-'*60}")
            log.info(f"⚠️  即将回滚以下操作:")
            log.info(f"    - 时间: {last_step['timestamp']}")
            log.info(f"    - 动作: {last_step['action_description']}")
            log.info(f"    - 当前历史步数: {history_count_before}")
            log.info(f"{'-'*60}")

            confirm = input("确认撤销此操作? (y/N，默认不撤销): ").strip().lower()

            if confirm != 'y':
                log.info("🔒 回滚操作已取消")
                continue

            # 执行回滚
            log.info(f"[Rollback] 开始回滚操作")
            log.info(f"[Rollback] 回滚前历史记录数: {history_count_before}")
            log.info(f"[Rollback] 回滚的操作: {last_step['action_description']}")
            log.info(f"[Rollback] 操作时间: {last_step['timestamp']}")

            if history_manager.rollback():
                history_count_after = history_manager.get_history_count()
                log.info(f"[Rollback] 回滚后历史记录数: {history_count_after}")
                log.info("✅ 回滚成功！")
                # 回滚后保存文件到磁盘
                save_to_disk(config.OUTPUT_SCRIPT_FILE, history_manager.get_current_file_content())
            else:
                log.error("❌ 回滚失败")
            continue

        try:
            # 等待 App 空闲（无动态加载转圈）
            device.wait_activity(device.app_current()['activity'], timeout=3)
        except Exception:
            time.sleep(1)

        log.info("[System] 抓取并压缩 XML 树")

        ui_json = compress_android_xml(device.dump_hierarchy())
        action_data = brain.get_action(cmd, ui_json)

        if action_data:
            log.debug(f"[Debug] 动作数据: {action_data}")
            result = executor.execute_and_record(action_data)
            log.debug(f"[Debug] 执行结果: {result}")
            log.debug(f"[Debug] Success: {result.get('success')}")
            log.debug(f"[Debug] 代码行数: {len(result.get('code_lines', []))}")
            if result["code_lines"]:
                log.debug(f"[Debug] 生成的代码行: {result['code_lines']}")

            if result.get("success"):
                log.debug("[Debug] 执行动作成功，添加到历史记录")
                history_manager.add_step(result["code_lines"], result["action_description"])
                log.debug(f"[Debug] 当前历史记录数: {history_manager.get_history_count()}")
                current_content = history_manager.get_current_file_content()
                log.debug(f"[Debug] 当前文件内容行数: {len(current_content)}")
                # 保存到磁盘
                save_to_disk(config.OUTPUT_SCRIPT_FILE, current_content)
                log.debug(f"[Debug] 已保存 {len(result['code_lines'])} 行代码到 {config.OUTPUT_SCRIPT_FILE}")
            else:
                log.error("[System] ❌ 执行动作失败")
        else:
            log.error("[System] ❌ 动作解析失败，请换一种描述。")


if __name__ == "__main__":
    main()
