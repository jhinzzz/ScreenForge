import os
import sys
import time
import base64
import argparse
from datetime import datetime

import uiautomator2 as u2

from common.ai import AIBrain
from common.logs import log
from common.executor import UIExecutor
from common.history_manager import StepHistoryManager
from common.adapters import AndroidU2Adapter, IosWdaAdapter, WebPlaywrightAdapter
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
        '    """回放自动录制的 UI 步骤"""\n',
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


def launch_app(device, env_name="dev", system="android"):
    """启动指定环境的 App"""
    app = _get_app_config(env_name, system)
    if app and system == "android":
        device.app_start(app)
        log.info(f"✅ App 已启动: {app}")


def _get_app_config(env_name="dev", system="android"):
    """获取指定环境的 App 配置"""
    return config.APP_ENV_CONFIG.get(env_name, {}).get(system)


def main():
    parser = argparse.ArgumentParser(description="多端人机交互 UI 测试录制引擎")
    parser.add_argument(
        "--platform",
        type=str,
        default="android",
        choices=["android", "ios", "web"],
        help="目标测试平台",
    )
    parser.add_argument("--env", type=str, default="dev", help="测试环境")
    args = parser.parse_args()

    # 动态目录
    base_dir = os.path.abspath(os.path.dirname(__file__))
    platform_dir = os.path.join(base_dir, "test_cases", args.platform)
    os.makedirs(platform_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    current_script_path = os.path.join(platform_dir, f"test_auto_{timestamp}.py")

    log.info("=" * 50)
    log.info(f"🚀 AI 测试录制引擎 (Interactive Mode) | 平台: {args.platform}")
    log.info(f"📁 临时存档路径: {current_script_path}")
    log.info("=" * 50)

    try:
        # 使用工厂模式根据参数分发适配器，取代写死的 u2.connect()
        if args.platform == "android":
            adapter = AndroidU2Adapter()
        elif args.platform == "ios":
            adapter = IosWdaAdapter()
        elif args.platform == "web":
            adapter = WebPlaywrightAdapter()
        else:
            raise ValueError(f"不支持的平台: {args.platform}")

        adapter.setup()
        device = adapter.driver
        log.info(f"✅ {args.platform} 平台已连接并初始化完成")
    except Exception as e:
        log.error(f"❌ 设备/浏览器连接失败: {e}")
        sys.exit(1)

    launch_app(device, args.env, args.platform)

    # 初始化历史管理器，传入初始头部内容
    initial_header = get_initial_header()
    history_manager = StepHistoryManager(initial_content=initial_header)

    # 保存初始文件到磁盘
    save_to_disk(config.OUTPUT_SCRIPT_FILE, initial_header)
    log.info(f"✅ 测试脚本已创建: {config.OUTPUT_SCRIPT_FILE}")
    log.info("✅ 待操作 AI 填入测试用例内容")

    brain = AIBrain()
    executor = UIExecutor(device)

    vision_mode = False  # 热插拔视觉多模态开关

    try:
        while True:
            history_count = history_manager.get_history_count()
            cache_status = "✅" if brain.cache_manager.enabled else "❌"
            vision_status = "✅" if vision_mode else "❌"
            print(f"\n[步数: {history_count}] [缓存: {cache_status}] [视觉: {vision_status}]")
            prompt = "请输入指令 (q退出, u撤销, v-on/off视觉) : "
            cmd = input(prompt).strip()

            if not cmd:
                continue

            if cmd.lower() in ["exit", "q", "quit"]:
                log.info("🎉 [System] 录制结束")
                log.info(f"💡 [System] 请输入最终测试用例名称 (直接回车保留默认名: {os.path.basename(current_script_path)}): ")
                new_name = input("请输入最终测试用例名称: ").strip()
                if new_name:
                    if not new_name.startswith("test_"):
                        new_name = "test_" + new_name
                    if not new_name.endswith(".py"):
                        new_name += ".py"
                    # 重命名前的源文件存在性校验
                    new_path = os.path.join(platform_dir, new_name)
                    if os.path.exists(current_script_path):
                        os.rename(current_script_path, new_path)
                        current_script_path = new_path
                    else:
                        log.warning(f"⚠️ [Warning] 无法重命名，源文件异常丢失: {current_script_path}")

                log.info(f"🏁 [System] 用例已成功落地: {current_script_path}")
                log.info(f"▶️ [System] 运行命令验证: pytest {current_script_path}")
                break

            if cmd.lower() == "v-on":
                vision_mode = True
                log.info("✅ [System] 视觉多模态辅助已开启。下一次指令将附带屏幕截图发给 AI。")
                continue

            if cmd.lower() == "v-off":
                vision_mode = False
                log.info("❌ [System] 视觉多模态辅助已关闭。下一次指令将使用纯文本模式。")
                continue

            if cmd.lower() == "cache":
                stats = brain.cache_manager.get_stats()
                log.info(f"\n{'=' * 60}")
                log.info("📊 缓存统计信息")
                log.info(f"{'=' * 60}")
                log.info(
                    f"缓存状态: {'✅ 已启用' if brain.cache_manager.enabled else '❌ 已禁用'}"
                )
                log.info(f"总查询次数: {stats['total_queries']}")
                log.info(f"缓存命中: {stats['cache_hits']}")
                log.info(f"缓存未命中: {stats['cache_misses']}")
                log.info(f"命中率: {stats['hit_rate']:.2%}")
                log.info(f"节省的 API 调用: {stats['total_api_calls_saved']}")
                if stats.get("first_cache_date"):
                    log.info(f"首次缓存时间: {stats['first_cache_date']}")
                if stats.get("last_cache_date"):
                    log.info(f"最后缓存时间: {stats['last_cache_date']}")
                log.info(f"{'=' * 60}")
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
                log.info(f"\n{'-' * 60}")
                log.info("⚠️  即将回滚以下操作:")
                log.info(f"    - 时间: {last_step['timestamp']}")
                log.info(f"    - 动作: {last_step['action_description']}")
                log.info(f"    - 当前历史步数: {history_count_before}")
                log.info(f"{'-' * 60}")

                confirm = input("确认撤销此操作? (y/N，默认不撤销): ").strip().lower()

                if confirm != "y":
                    log.info("🔒 回滚操作已取消")
                    continue

                # 执行回滚
                log.info("🔙 [Rollback] 开始回滚操作")
                log.info(f"🔙 [Rollback] 回滚前历史记录数: {history_count_before}")
                log.info(f"🔙 [Rollback] 回滚的操作: {last_step['action_description']}")
                log.info(f"🔙 [Rollback] 操作时间: {last_step['timestamp']}")

                if history_manager.rollback():
                    history_count_after = history_manager.get_history_count()
                    log.info(f"🔙 [Rollback] 回滚后历史记录数: {history_count_after}")
                    # 回滚后保存文件到磁盘
                    save_to_disk(current_script_path, history_manager.get_current_file_content())
                    log.info("✅ [Rollback] ✅ 回滚成功")
                else:
                    log.error("❌ [Rollback] ❌ 回滚失败")
                continue

            try:
                # 等待 App 空闲（仅安卓生效）
                if args.platform == "android":
                    device.wait_activity(device.app_current()["activity"], timeout=3)
            except Exception:
                time.sleep(1)

            log.info("⏳ [System] 抓取页面结构与截图...")

            ui_json = (
                compress_android_xml(device.dump_hierarchy())
                if args.platform == "android"
                else "{}"
            )

            # 多模态视觉注入
            screenshot_base64 = None
            if vision_mode:
                try:
                    img_bytes = adapter.take_screenshot()
                    screenshot_base64 = base64.b64encode(img_bytes).decode("utf-8")
                except Exception as e:
                    log.warning(f"⚠️ 截图失败，将降级为纯文本模型: {e}")

            current_history = history_manager.get_history()
            # 取最近 5 条历史记录作为上下文
            # 防止出现历史记录过长导致的 AI 幻觉和 token 地狱
            recent_context = current_history[-5:] if len(current_history) > 5 else current_history

            action_data = brain.get_action(
                instruction=cmd,
                ui_json=ui_json,
                screenshot_base64=screenshot_base64,
                chat_history=recent_context
            )

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
                    log.debug(
                        f"[Debug] 当前历史记录数: {history_manager.get_history_count()}"
                    )
                    current_content = history_manager.get_current_file_content()
                    log.debug(f"[Debug] 当前文件内容行数: {len(current_content)}")
                    # 保存到磁盘
                    save_to_disk(current_script_path, history_manager.get_current_file_content())
                    log.debug(
                        f"[Debug] 已保存 {len(result['code_lines'])} 行代码到 {config.OUTPUT_SCRIPT_FILE}"
                    )
                else:
                    log.error("[System] ❌ 执行动作失败")
            else:
                log.error("[System] ❌ 动作解析失败，请换一种描述。")

    except KeyboardInterrupt:
        log.warning("\n⚠️ 收到中断信号 (KeyboardInterrupt)，正在安全退出...")
    finally:
        # 安全断开设备释放资源
        try:
            adapter.teardown()
        except Exception as e:
            log.warning(f"⚠️ [Warning] 清理资源时发生异常: {e}")


if __name__ == "__main__":
    main()
