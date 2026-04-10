"""CLI argument parser and validation."""

import argparse

from common.runtime_modes import resolve_execution_mode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="多端自动化测试自主 Agent 底层执行器")
    parser.add_argument("--goal", type=str, default="", help="宏观测试目标")
    parser.add_argument(
        "--context", type=str, default="", help="包含 PRD、用例详细说明的文件路径"
    )
    parser.add_argument(
        "--env",
        type=str,
        default="dev",
        choices=["dev", "prod", "us_dev", "us_prod"],
        help="测试环境",
    )
    parser.add_argument("--max_steps", type=int, default=15, help="最大自主探索步数")
    parser.add_argument(
        "--max_retries",
        type=int,
        default=3,
        help="单步操作的最大连续容错重试次数，防 Token 消耗死循环",
    )
    parser.add_argument(
        "--output", type=str, default="", help="指定生成的 pytest 脚本路径"
    )
    parser.add_argument(
        "--platform",
        type=str,
        default="android",
        choices=["android", "ios", "web"],
        help="目标测试平台",
    )
    parser.add_argument(
        "--vision", action="store_true", help="是否开启多模态(视觉)模式"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="是否向 stdout 输出结构化 JSON 事件，便于上层 Agent 解析",
    )
    parser.add_argument(
        "--doctor", action="store_true", help="仅执行环境体检，不启动测试执行"
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="基于当前页面生成执行计划，但不执行物理动作",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="模拟执行链路并输出 would-execute 结果，但不执行物理动作",
    )
    parser.add_argument(
        "--resume-run-id",
        type=str,
        default="",
        help="从 report/runs/<run_id>/ 中恢复最小上下文",
    )
    parser.add_argument(
        "--workflow",
        type=str,
        default="",
        help="指定结构化 workflow YAML 文件路径，启用半结构化执行模式",
    )
    parser.add_argument(
        "--workflow-var",
        action="append",
        default=[],
        help="覆盖 workflow 变量，格式为 KEY=VALUE，可重复传入",
    )
    parser.add_argument(
        "--action",
        type=str,
        default="",
        help="指定单步即时动作，启用最小控制面模式",
    )
    parser.add_argument(
        "--action-name",
        type=str,
        default="",
        help="指定单步即时动作的人类可读名称",
    )
    parser.add_argument(
        "--locator-type",
        type=str,
        default="",
        help="指定单步即时动作的定位器类型",
    )
    parser.add_argument(
        "--locator-value",
        type=str,
        default="",
        help="指定单步即时动作的定位器值",
    )
    parser.add_argument(
        "--extra-value",
        type=str,
        default="",
        help="指定单步即时动作附加值，如输入内容、按键名或期望文本",
    )
    parser.add_argument(
        "--capabilities",
        action="store_true",
        help="输出当前 CLI 已落地能力的机器可读快照",
    )
    parser.add_argument(
        "--tool-request",
        type=str,
        default="",
        help="从 JSON 文件读取机器可读请求并返回统一 JSON 响应",
    )
    parser.add_argument(
        "--tool-stdin",
        action="store_true",
        help="从 stdin 读取机器可读请求并返回统一 JSON 响应",
    )
    parser.add_argument(
        "--mcp-server",
        action="store_true",
        help="以 stdio 模式启动最小 MCP server，供外部 Agent 原生接入",
    )
    return parser


def validate_cli_args(args) -> None:
    resolve_execution_mode(
        doctor=args.doctor,
        plan_only=args.plan_only,
        dry_run=args.dry_run,
    )
    has_goal = bool(str(args.goal).strip())
    has_workflow = bool(str(getattr(args, "workflow", "")).strip())
    has_action = bool(str(getattr(args, "action", "")).strip())
    has_capabilities = bool(getattr(args, "capabilities", False))
    has_tool_request = bool(str(getattr(args, "tool_request", "")).strip())
    has_tool_stdin = bool(getattr(args, "tool_stdin", False))
    has_mcp_server = bool(getattr(args, "mcp_server", False))
    if has_tool_request and has_tool_stdin:
        raise ValueError("--tool-request 不能与 --tool-stdin 同时使用")
    if has_mcp_server:
        if any(
            [
                has_capabilities,
                has_tool_request,
                has_tool_stdin,
                args.doctor,
                args.plan_only,
                args.dry_run,
                has_goal,
                has_workflow,
                has_action,
                bool(str(getattr(args, "resume_run_id", "")).strip()),
            ]
        ):
            raise ValueError("--mcp-server 不能与执行类参数同时使用")
        return
    if has_tool_request:
        if any(
            [
                has_capabilities,
                has_tool_stdin,
                has_mcp_server,
                args.doctor,
                args.plan_only,
                args.dry_run,
                has_goal,
                has_workflow,
                has_action,
                bool(str(getattr(args, "resume_run_id", "")).strip()),
            ]
        ):
            raise ValueError("--tool-request 不能与执行类参数同时使用")
        return
    if has_tool_stdin:
        if any(
            [
                has_capabilities,
                has_mcp_server,
                args.doctor,
                args.plan_only,
                args.dry_run,
                has_goal,
                has_workflow,
                has_action,
                bool(str(getattr(args, "resume_run_id", "")).strip()),
            ]
        ):
            raise ValueError("--tool-stdin 不能与执行类参数同时使用")
        return
    if has_capabilities:
        if any(
            [
                args.doctor,
                args.plan_only,
                args.dry_run,
                has_goal,
                has_workflow,
                has_action,
                has_tool_request,
                has_tool_stdin,
                has_mcp_server,
            ]
        ):
            raise ValueError("--capabilities 不能与执行类参数同时使用")
        return
    if has_goal and has_workflow:
        raise ValueError("--workflow 模式下不能同时提供 --goal")
    if has_action and (has_goal or has_workflow):
        raise ValueError("--action 模式下不能同时提供 --goal 或 --workflow")
    if not args.doctor and not has_goal and not has_workflow and not has_action:
        raise ValueError("非 doctor 模式必须提供 --goal、--workflow 或 --action")
    if has_workflow:
        for item in getattr(args, "workflow_var", []) or []:
            if "=" not in str(item):
                raise ValueError("workflow 变量覆盖格式必须为 KEY=VALUE")
    if has_action:
        from common.capabilities import (
            ACTIONS_REQUIRING_EXTRA_VALUE,
            GLOBAL_ACTIONS,
            SUPPORTED_ACTIONS,
        )

        action = str(args.action).strip()
        if action not in SUPPORTED_ACTIONS:
            raise ValueError(f"不支持的即时动作类型: {action}")
        if action not in GLOBAL_ACTIONS:
            if not str(getattr(args, "locator_type", "")).strip() or not str(
                getattr(args, "locator_value", "")
            ).strip():
                raise ValueError("元素类即时动作必须提供 locator_type 和 locator_value")
        if action in ACTIONS_REQUIRING_EXTRA_VALUE and not str(
            getattr(args, "extra_value", "")
        ).strip():
            raise ValueError("该即时动作必须提供 extra_value")
