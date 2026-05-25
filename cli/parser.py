"""CLI argument parser and validation."""

import argparse

from cli._version import __version__
from common.runtime_modes import resolve_execution_mode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="screenforge",
        description="AI-driven cross-platform UI automation engine",
    )
    parser.add_argument("--version", action="version", version=f"screenforge {__version__}")
    parser.add_argument("--goal", type=str, default="", help="High-level test goal (natural language)")
    parser.add_argument(
        "--context", type=str, default="", help="Path to PRD or test case specification file"
    )
    parser.add_argument(
        "--env",
        type=str,
        default="dev",
        choices=["dev", "prod", "us_dev", "us_prod"],
        help="Target environment (default: dev)",
    )
    parser.add_argument("--max_steps", type=int, default=15, help="Max autonomous exploration steps")
    parser.add_argument(
        "--max_retries",
        type=int,
        default=3,
        help="Max retries per step before circuit breaker triggers",
    )
    parser.add_argument(
        "--output", type=str, default="", help="Output path for generated pytest script"
    )
    parser.add_argument(
        "--platform",
        type=str,
        default="web",
        choices=["android", "ios", "web"],
        help="Target platform (default: web)",
    )
    parser.add_argument(
        "--vision", action="store_true", help="Enable multimodal (vision) mode"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit structured JSON events to stdout for Agent integration",
    )
    parser.add_argument(
        "--doctor", action="store_true", help="Run environment diagnostics only"
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Generate execution plan without performing actions",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate execution and output would-execute results",
    )
    parser.add_argument(
        "--resume-run-id",
        type=str,
        default="",
        help="Resume from a previous run (reads report/runs/<run_id>/)",
    )
    parser.add_argument(
        "--workflow",
        type=str,
        default="",
        help="Path to structured workflow YAML file",
    )
    parser.add_argument(
        "--workflow-var",
        action="append",
        default=[],
        help="Override workflow variable (KEY=VALUE, repeatable)",
    )
    parser.add_argument(
        "--action",
        type=str,
        default="",
        help="Execute a single immediate action (click, input, goto, etc.)",
    )
    parser.add_argument(
        "--action-name",
        type=str,
        default="",
        help="Human-readable name for the action (for reporting)",
    )
    parser.add_argument(
        "--locator-type",
        type=str,
        default="",
        help="Locator strategy: css, text, resourceId, description, ref",
    )
    parser.add_argument(
        "--locator-value",
        type=str,
        default="",
        help="Locator value to find the target element",
    )
    parser.add_argument(
        "--extra-value",
        type=str,
        default="",
        help="Extra value for action (input text, key name, expected text, URL)",
    )
    parser.add_argument(
        "--capabilities",
        action="store_true",
        help="Output machine-readable capability snapshot",
    )
    parser.add_argument(
        "--tool-request",
        type=str,
        default="",
        help="Read request from JSON file and return unified JSON response",
    )
    parser.add_argument(
        "--tool-stdin",
        action="store_true",
        help="Read request from stdin and return unified JSON response",
    )
    parser.add_argument(
        "--mcp-server",
        action="store_true",
        help="Start MCP server (stdio transport) for Agent integration",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run simulated demo (no API key needed)",
    )
    parser.add_argument(
        "--playground",
        action="store_true",
        help="Start Playground web UI (live screenshot viewer + action history)",
    )
    parser.add_argument(
        "--playground-port",
        type=int,
        default=7860,
        help="Playground server port (default: 7860)",
    )
    return parser


def validate_cli_args(args: argparse.Namespace) -> None:
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
        raise ValueError("--tool-request and --tool-stdin are mutually exclusive")
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
            raise ValueError("--mcp-server cannot be combined with other execution flags")
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
            raise ValueError("--tool-request cannot be combined with other execution flags")
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
            raise ValueError("--tool-stdin cannot be combined with other execution flags")
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
            raise ValueError("--capabilities cannot be combined with other execution flags")
        return
    if has_goal and has_workflow:
        raise ValueError("--goal and --workflow are mutually exclusive")
    if has_action and (has_goal or has_workflow):
        raise ValueError("--action cannot be combined with --goal or --workflow")
    has_demo = bool(getattr(args, "demo", False))
    if has_demo:
        return
    if not args.doctor and not has_goal and not has_workflow and not has_action:
        raise ValueError("Must provide --goal, --workflow, or --action (use --doctor for diagnostics)")
    if has_workflow:
        for item in getattr(args, "workflow_var", []) or []:
            if "=" not in str(item):
                raise ValueError("--workflow-var format must be KEY=VALUE")
    if has_action:
        from common.capabilities import (
            ACTIONS_REQUIRING_EXTRA_VALUE,
            GLOBAL_ACTIONS,
            SUPPORTED_ACTIONS,
        )

        action = str(args.action).strip()
        if action not in SUPPORTED_ACTIONS:
            raise ValueError(f"Unsupported action: {action}")
        if action not in GLOBAL_ACTIONS:
            if not str(getattr(args, "locator_type", "")).strip() or not str(
                getattr(args, "locator_value", "")
            ).strip():
                raise ValueError("Element actions require --locator-type and --locator-value")
        if action in ACTIONS_REQUIRING_EXTRA_VALUE and not str(
            getattr(args, "extra_value", "")
        ).strip():
            raise ValueError(f"Action '{action}' requires --extra-value")
