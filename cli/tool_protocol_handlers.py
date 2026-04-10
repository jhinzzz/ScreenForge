"""Tool protocol handlers: MCP server, tool-request, tool-stdin, inspect_ui."""

import base64
import json
import sys
from contextlib import nullcontext
from pathlib import Path

from common.run_resume import RunContextLoadError, load_run_bundle
from common.runtime_modes import MODE_DOCTOR, resolve_execution_mode
from common.tool_protocol import (
    ToolRequestError,
    build_capabilities_response,
    build_cli_arg_overrides,
    load_tool_request,
    load_tool_request_from_stdin,
)

from cli.parser import build_parser, validate_cli_args
from cli.reporter import (
    _build_inline_action_data,
    _load_context_content,
    _resolve_control_identity,
    _resolve_output_script_path,
)
from cli.shared import (
    _SharedAdapterManager,
    _capture_ui_state,
    _connect_adapter,
    config,
    log,
)


class _NullRunReporter:
    def emit_event(self, event: str, **payload) -> None:
        return None

    def save_screenshot(self, img_bytes: bytes, step_index: int, name: str | None = None) -> str:
        return ""


def _list_run_dirs(base_dir: Path) -> set[Path]:
    if not base_dir.exists():
        return set()
    return {item for item in base_dir.iterdir() if item.is_dir()}


def _resolve_new_run_dir(before: set[Path], base_dir: Path) -> Path | None:
    after = _list_run_dirs(base_dir)
    new_dirs = sorted(after - before)
    if new_dirs:
        return new_dirs[-1]
    if not after:
        return None
    return sorted(after)[-1]


def _emit_tool_response(payload: dict) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    sys.stdout.flush()
    return int(payload.get("exit_code", 0))


def _empty_run_assets() -> dict:
    return {
        "summary_path": "",
        "artifacts_path": "",
        "pytest_replay_path": "",
        "failure_analysis": {},
        "pytest_asset": {},
        "resume_commands": {},
        "recommended_next_step": None,
    }


def _load_run_assets(run_dir: Path | None) -> dict:
    if not run_dir:
        return {
            "summary": {},
            "run_assets": _empty_run_assets(),
            "resume_context": {},
        }

    bundle = load_run_bundle(run_dir)
    return {
        "summary": bundle.get("summary", {}) or {},
        "run_assets": bundle.get("run_assets", {}) or _empty_run_assets(),
        "resume_context": bundle.get("resume_context", {}) or {},
    }


def _load_case_memory_store():
    from common.case_memory import CaseMemoryStore

    return CaseMemoryStore()


def _find_case_memory_hit(args, execution_mode: str) -> dict | None:
    if execution_mode == MODE_DOCTOR:
        return None

    control_identity = _resolve_control_identity(args, execution_mode)
    control_kind = str(control_identity.get("control_kind", "")).strip()
    if control_kind == "doctor":
        return None

    return _load_case_memory_store().find_entry(
        platform=args.platform,
        control_kind=control_kind,
        control_label=control_identity.get("control_label", ""),
        source_ref=control_identity.get("control_source_ref", ""),
    )


def build_load_case_memory_payload(
    platform: str = "",
    control_kind: str = "",
    query: str = "",
    source_ref: str = "",
    limit: int = 20,
) -> dict:
    entries = _load_case_memory_store().query_entries(
        platform=platform,
        control_kind=control_kind,
        query=query,
        source_ref=source_ref,
        limit=limit,
    )
    return {
        "ok": True,
        "operation": "load_case_memory",
        "exit_code": 0,
        "case_memory_path": str(config.CASE_MEMORY_PATH),
        "entries": entries,
    }


def build_inspect_ui_payload(request, shared_adapter_manager: _SharedAdapterManager | None = None) -> dict:
    parser = build_parser()
    request_args = parser.parse_args([])
    request_args.platform = request.platform
    request_args.env = request.env
    request_args.vision = request.vision

    adapter = None
    owns_adapter = False
    try:
        if shared_adapter_manager:
            adapter = shared_adapter_manager.get_or_create(request.platform, request.env)
        else:
            adapter = _connect_adapter(request_args, _NullRunReporter())
            owns_adapter = True
        ui_json, screenshot_base64 = _capture_ui_state(
            request_args,
            adapter,
            _NullRunReporter(),
            1,
        )

        # inspect_ui 始终截图 (不受 --vision 开关限制)
        if not screenshot_base64:
            try:
                img_bytes = adapter.take_screenshot()
                screenshot_base64 = base64.b64encode(img_bytes).decode("utf-8")
            except Exception as e:
                log.warning(f"⚠️ [Warning] inspect_ui 截图失败: {e}")

        try:
            ui_tree = json.loads(ui_json)
        except json.JSONDecodeError:
            ui_tree = {"ui_elements": [], "raw": ui_json}

        # 生成标注截图 (红框 + ref 标签)
        annotated_screenshot_base64 = ""
        if screenshot_base64 and ui_tree.get("ui_elements"):
            try:
                from utils.screenshot_annotator import annotate_screenshot
                raw_bytes = base64.b64decode(screenshot_base64)
                annotated_bytes = annotate_screenshot(raw_bytes, ui_tree["ui_elements"])
                annotated_screenshot_base64 = base64.b64encode(annotated_bytes).decode("utf-8")
            except Exception as e:
                log.warning(f"⚠️ [Warning] 生成标注截图失败: {e}")

        return {
            "ok": True,
            "operation": "inspect_ui",
            "exit_code": 0,
            "platform": request.platform,
            "env": request.env,
            "ui_json": ui_json,
            "ui_tree": ui_tree,
            "element_count": len(ui_tree.get("ui_elements", []) or []),
            "screenshot_base64": screenshot_base64 or "",
            "annotated_screenshot_base64": annotated_screenshot_base64,
        }
    except Exception as e:
        return {
            "ok": False,
            "operation": "inspect_ui",
            "exit_code": 1,
            "platform": request.platform,
            "env": request.env,
            "error": str(e),
        }
    finally:
        if owns_adapter and adapter:
            try:
                adapter.teardown()
            except Exception as e:
                log.warning(f"⚠️ [Warning] 清理资源时发生异常: {e}")


def _requires_model_runtime(args, execution_mode: str) -> bool:
    if execution_mode == MODE_DOCTOR:
        return False
    if str(getattr(args, "workflow", "")).strip():
        return False
    if str(getattr(args, "action", "")).strip():
        return False
    return bool(str(getattr(args, "goal", "")).strip())


def build_tool_response_payload(request, shared_adapter_manager: _SharedAdapterManager | None = None) -> dict:
    if request.operation == "capabilities":
        payload = build_capabilities_response()
        payload["exit_code"] = 0
        return payload
    if request.operation == "load_run":
        return build_load_run_payload(request.run_id)
    if request.operation == "load_case_memory":
        return build_load_case_memory_payload(
            platform=request.platform,
            control_kind=request.control_kind,
            query=request.query,
            source_ref=request.source_ref,
            limit=request.limit,
        )
    if request.operation == "inspect_ui":
        return build_inspect_ui_payload(request, shared_adapter_manager=shared_adapter_manager)

    parser = build_parser()
    request_args = parser.parse_args([])
    for key, value in build_cli_arg_overrides(request).items():
        setattr(request_args, key, value)

    try:
        validate_cli_args(request_args)
    except ValueError as e:
        return {
            "ok": False,
            "operation": "execute",
            "exit_code": 2,
            "error": str(e),
        }

    execution_mode = resolve_execution_mode(
        doctor=request_args.doctor,
        plan_only=request_args.plan_only,
        dry_run=request_args.dry_run,
    )
    case_memory_hit = _find_case_memory_hit(request_args, execution_mode)
    output_script_path = _resolve_output_script_path(request_args)
    run_base_dir = Path(config.RUN_REPORT_BASE_DIR)
    previous_run_dirs = _list_run_dirs(run_base_dir)

    try:
        context_content, resume_context = _load_context_content(request_args)
    except RunContextLoadError as e:
        return {
            "ok": False,
            "operation": "execute",
            "exit_code": 2,
            "mode": execution_mode,
            "error": str(e),
        }

    if _requires_model_runtime(request_args, execution_mode) and not config.validate_config():
        return {
            "ok": False,
            "operation": "execute",
            "exit_code": 1,
            "mode": execution_mode,
            "error": "配置校验失败",
        }

    mute_logs_context = nullcontext
    try:
        from common.logs import mute_stderr_logs as _mute_stderr_logs

        mute_logs_context = _mute_stderr_logs
    except Exception:
        mute_logs_context = nullcontext

    from cli.dispatch import _dispatch_execution

    with mute_logs_context():
        exit_code = _dispatch_execution(
            request_args,
            execution_mode,
            output_script_path,
            context_content,
            resume_context,
            shared_adapter_manager=shared_adapter_manager,
        )
    run_dir = _resolve_new_run_dir(previous_run_dirs, run_base_dir)
    loaded_assets = _load_run_assets(run_dir) if run_dir and (run_dir / "summary.json").exists() else {
        "summary": {},
        "run_assets": _empty_run_assets(),
        "resume_context": {},
    }
    summary = loaded_assets["summary"]
    run_assets = loaded_assets["run_assets"]
    summary_path = run_assets.get("summary_path", "")

    return {
        "ok": exit_code == 0,
        "operation": "execute",
        "mode": execution_mode,
        "exit_code": exit_code,
        "run_dir": str(run_dir) if run_dir else "",
        "summary_path": summary_path,
        "summary": summary,
        "run_assets": run_assets,
        "case_memory_hit": bool(case_memory_hit),
        "case_memory_entry": summary.get("case_memory_entry") or case_memory_hit,
        "recommended_next_step": run_assets.get("recommended_next_step"),
    }


def build_load_run_payload(run_id: str) -> dict:
    run_id = str(run_id).strip()
    run_dir = Path(config.RUN_REPORT_BASE_DIR) / run_id
    try:
        bundle = load_run_bundle(run_dir)
    except RunContextLoadError as e:
        return {
            "ok": False,
            "operation": "load_run",
            "exit_code": 2,
            "run_id": run_id,
            "error": str(e),
            "run_assets": _empty_run_assets(),
        }

    run_assets = bundle.get("run_assets", {}) or _empty_run_assets()
    return {
        "ok": True,
        "operation": "load_run",
        "exit_code": 0,
        "run_id": bundle.get("run_id", "") or run_id,
        "run_dir": bundle.get("run_dir", str(run_dir)),
        "summary_path": run_assets.get("summary_path", ""),
        "summary": bundle.get("summary", {}) or {},
        "run_assets": run_assets,
        "recommended_next_step": run_assets.get("recommended_next_step"),
        "resume_context": bundle.get("resume_context", {}) or {},
    }


def _run_tool_request(request) -> int:
    return _emit_tool_response(build_tool_response_payload(request))


def run_tool_request_mode(args) -> int:
    try:
        request = load_tool_request(args.tool_request)
    except ToolRequestError as e:
        return _emit_tool_response(
            {
                "ok": False,
                "operation": "tool_request",
                "exit_code": 2,
                "error": str(e),
            }
        )
    return _run_tool_request(request)


def run_tool_stdin_mode(args) -> int:
    try:
        request = load_tool_request_from_stdin(sys.stdin.read())
    except ToolRequestError as e:
        return _emit_tool_response(
            {
                "ok": False,
                "operation": "tool_stdin",
                "exit_code": 2,
                "error": str(e),
            }
        )
    return _run_tool_request(request)


def run_mcp_server_mode(args) -> int:
    from functools import partial

    from common.mcp_server import run_stdio_mcp_server

    shared_mgr = _SharedAdapterManager()
    try:
        return run_stdio_mcp_server(
            partial(build_tool_response_payload, shared_adapter_manager=shared_mgr),
            build_load_run_payload,
            partial(build_inspect_ui_payload, shared_adapter_manager=shared_mgr),
            lambda request: build_load_case_memory_payload(
                platform=request.platform,
                control_kind=request.control_kind,
                query=request.query,
                source_ref=request.source_ref,
                limit=request.limit,
            ),
        )
    finally:
        shared_mgr.teardown_all()
