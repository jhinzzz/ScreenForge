"""Doctor mode: environment health checks and remediation."""

import json
import os
import sys
from pathlib import Path

from common.capabilities import get_capabilities_payload
from common.runtime_modes import MODE_DOCTOR

from cli.reporter import _build_reporter, _emit_run_started
from cli.shared import (
    _ensure_preflight_runner,
    config,
    log,
    run_preflight,
)


def _normalize_doctor_message(message: str) -> str:
    lines = [line.strip() for line in str(message).splitlines() if line.strip()]
    return lines[0] if lines else ""


def _iter_doctor_check_findings(check: dict):
    for issue in check.get("issues", []) or []:
        text = _normalize_doctor_message(issue)
        if text:
            yield "issue", text

    for error in check.get("errors", []) or []:
        text = _normalize_doctor_message(error)
        if text:
            yield "error", text

    error_text = _normalize_doctor_message(check.get("error", ""))
    if error_text:
        yield "error", error_text

    hint_text = _normalize_doctor_message(check.get("hint", ""))
    if hint_text:
        yield "hint", hint_text


def _classify_doctor_check(check: dict) -> dict:
    check_name = str(check.get("name", "")).strip()

    if check_name == "config":
        return {"category": "config", "title": "配置问题", "priority": 1}
    if check_name in {"venv_consistency", "runtime_paths"}:
        return {"category": "runtime", "title": "运行时问题", "priority": 2}
    if check_name in {"adb", "uiautomator2", "wda", "playwright"}:
        return {"category": "dependency", "title": "依赖问题", "priority": 3}
    if check_name in {
        "adb_devices",
        "wda_status",
        "cdp_debug_endpoint",
        "http://localhost:8100",
        "http://localhost:9222",
    } or check_name.startswith(("http://", "https://")):
        return {"category": "connectivity", "title": "连接问题", "priority": 4}
    return {"category": "other", "title": "其他问题", "priority": 5}


def _doctor_fix_doc_reference(doc_name: str, section: str) -> dict:
    project_root = Path(__file__).resolve().parent.parent
    doc_path = project_root / doc_name
    return {
        "fix_doc": str(doc_path),
        "fix_doc_section": section,
    }


def _build_doctor_remediation(check_name: str, message: str) -> dict:
    message = str(message).strip()
    normalized_check_name = str(check_name).strip()
    common_doc = _doctor_fix_doc_reference(
        "docs/agent_guide.md", "排障"
    )

    remediation = {
        "fix_label": "查看诊断文档",
        "fix_command": "",
        **common_doc,
    }

    if normalized_check_name == "config":
        return {
            "fix_label": "补齐运行配置",
            "fix_command": "",
            **_doctor_fix_doc_reference("docs/agent_guide.md", "排障"),
        }

    if normalized_check_name == "venv_consistency":
        return {
            "fix_label": "修复虚拟环境入口漂移",
            "fix_command": "./.venv/bin/python scripts/repair_venv.py",
            **_doctor_fix_doc_reference("docs/agent_guide.md", "排障"),
        }

    if normalized_check_name == "runtime_paths":
        return {
            "fix_label": "确认运行目录可写",
            "fix_command": "",
            **_doctor_fix_doc_reference("docs/agent_guide.md", "排障"),
        }

    if normalized_check_name == "uiautomator2":
        return {
            "fix_label": "补齐 Android Python 依赖",
            "fix_command": "./.venv/bin/python -m pip install -r requirement.txt",
            **_doctor_fix_doc_reference("README.md", "安装 Python 依赖库"),
        }

    if normalized_check_name == "playwright":
        return {
            "fix_label": "安装 Playwright 依赖",
            "fix_command": "./.venv/bin/python -m pip install playwright",
            **_doctor_fix_doc_reference("README.md", "安装 Python 依赖库"),
        }

    if normalized_check_name == "wda":
        return {
            "fix_label": "安装 iOS WDA 依赖",
            "fix_command": "./.venv/bin/python -m pip install facebook-wda",
            **_doctor_fix_doc_reference("README.md", "安装 Python 依赖库"),
        }

    if normalized_check_name == "adb":
        return {
            "fix_label": "安装并暴露 adb 到 PATH",
            "fix_command": "",
            **_doctor_fix_doc_reference("docs/agent_guide.md", "排障"),
        }

    if normalized_check_name == "adb_devices":
        if "当前运行环境限制了" in message or "宿主终端" in message:
            return {
                "fix_label": "在宿主终端重试 adb 检查",
                "fix_command": "adb devices",
                **_doctor_fix_doc_reference("docs/agent_guide.md", "排障"),
            }
        return {
            "fix_label": "检查 Android 设备连接状态",
            "fix_command": "adb devices",
            **_doctor_fix_doc_reference("docs/agent_guide.md", "排障"),
        }

    if normalized_check_name in {"http://localhost:8100", "wda_status"}:
        return {
            "fix_label": "确认 WebDriverAgent 服务状态",
            "fix_command": "",
            **_doctor_fix_doc_reference("docs/agent_guide.md", "排障"),
        }

    if normalized_check_name in {"http://localhost:9222", "cdp_debug_endpoint"}:
        if "当前运行环境限制了" in message or "宿主终端" in message:
            return {
                "fix_label": "在宿主终端检查 Chrome DevTools 调试端口",
                "fix_command": "curl -sS http://localhost:9222/json/version",
                **_doctor_fix_doc_reference("docs/agent_guide.md", "排障"),
            }
        return {
            "fix_label": "确认 Chrome DevTools 调试端口",
            "fix_command": "",
            **_doctor_fix_doc_reference("docs/agent_guide.md", "排障"),
        }

    if "OPENAI_API_KEY" in message or "WEB_CDP_URL" in message:
        return {
            "fix_label": "补齐运行配置",
            "fix_command": "",
            **_doctor_fix_doc_reference("docs/agent_guide.md", "排障"),
        }

    return remediation


def _doctor_action_signature(category: str, item: dict) -> tuple:
    return (
        category,
        tuple(item.get("check_names", [])),
        item.get("fix_label", ""),
        item.get("fix_command", ""),
        item.get("fix_doc", ""),
        item.get("fix_doc_section", ""),
    )


def _append_recommended_action(actions: list[dict], category: str, priority: int, item: dict) -> None:
    candidate = {
        "category": category,
        "priority": priority,
        **item,
    }
    candidate_signature = _doctor_action_signature(category, item)

    for index, existing in enumerate(actions):
        existing_signature = _doctor_action_signature(existing.get("category", ""), existing)
        if existing_signature != candidate_signature:
            continue

        if candidate.get("kind") == "hint":
            actions[index] = candidate
            return

        if existing.get("kind") == "hint":
            return

    actions.append(candidate)


def _build_doctor_summary(checks: list[dict]) -> dict:
    groups = {}
    severity_rank = {"error": 0, "issue": 1, "hint": 2}

    for check in checks:
        if check.get("ok", False):
            continue

        group_meta = _classify_doctor_check(check)
        category = group_meta["category"]
        group = groups.setdefault(
            category,
            {
                "category": category,
                "title": group_meta["title"],
                "priority": group_meta["priority"],
                "items": [],
                "_item_map": {},
            },
        )

        check_name = str(check.get("name", "unknown")).strip() or "unknown"
        for kind, message in _iter_doctor_check_findings(check):
            remediation = _build_doctor_remediation(check_name, message)
            existing = group["_item_map"].get(message)
            if existing:
                if check_name not in existing["check_names"]:
                    existing["check_names"].append(check_name)
                if severity_rank[kind] < severity_rank[existing["kind"]]:
                    existing["kind"] = kind
                if not existing["fix_command"] and remediation.get("fix_command", ""):
                    existing["fix_command"] = remediation.get("fix_command", "")
                if existing.get("fix_doc_section", "") == "排障":
                    existing["fix_label"] = remediation.get("fix_label", existing["fix_label"])
                    existing["fix_doc"] = remediation.get("fix_doc", existing["fix_doc"])
                    existing["fix_doc_section"] = remediation.get(
                        "fix_doc_section", existing["fix_doc_section"]
                    )
                continue

            item = {
                "message": message,
                "kind": kind,
                "check_names": [check_name],
                "fix_label": remediation.get("fix_label", ""),
                "fix_command": remediation.get("fix_command", ""),
                "fix_doc": remediation.get("fix_doc", ""),
                "fix_doc_section": remediation.get("fix_doc_section", ""),
                "fix_priority": group["priority"],
            }
            group["_item_map"][message] = item
            group["items"].append(item)

    ordered_groups = sorted(
        groups.values(),
        key=lambda item: (item["priority"], item["category"]),
    )
    for group in ordered_groups:
        group.pop("_item_map", None)

    top_items = []
    recommended_actions = []
    for group in ordered_groups:
        for item in group["items"]:
            top_items.append(item["message"])
            _append_recommended_action(
                recommended_actions,
                group["category"],
                group["priority"],
                item,
            )

    return {
        "ok": not ordered_groups,
        "group_count": len(ordered_groups),
        "top_items": top_items,
        "groups": ordered_groups,
        "recommended_actions": recommended_actions,
    }


def _build_doctor_remediation_items(checks: list[dict]) -> list[str]:
    return _build_doctor_summary(checks).get("top_items", [])


def _build_doctor_check_failure_message(check: dict) -> str:
    details = []

    def add_detail(message: str) -> None:
        text = _normalize_doctor_message(message)
        if text and text not in details:
            details.append(text)

    for issue in check.get("issues", []) or []:
        add_detail(issue)

    for error in check.get("errors", []) or []:
        add_detail(error)

    add_detail(check.get("error", ""))

    if not details:
        if "path" in check and not str(check.get("path", "")).strip():
            details.append("未找到可执行文件")
        elif check.get("name") == "runtime_paths":
            details.append("运行时目录不可用或不可写")
        else:
            details.append("检查未通过")

    return f"   - {check.get('name', 'unknown')}: {'；'.join(details)}"


def run_doctor_mode(args, output_script_path: str) -> int:
    reporter = _build_reporter(args, output_script_path, MODE_DOCTOR)
    final_status = "failed"
    exit_code = 1
    final_error = ""
    _emit_run_started(reporter, args, output_script_path, MODE_DOCTOR)

    try:
        _ensure_preflight_runner()
        result = run_preflight(
            platform=args.platform,
            script_dir=Path(os.path.dirname(os.path.abspath(output_script_path))),
            run_dir=Path(config.RUN_REPORT_BASE_DIR),
        )
        for check in result.get("checks", []):
            reporter.emit_event(
                "doctor_check",
                check_name=check.get("name", ""),
                success=check.get("ok", False),
                detail=check,
            )
        doctor_summary = _build_doctor_summary(result.get("checks", []))
        reporter.update_summary(doctor_summary=doctor_summary)
        reporter.emit_event(
            "doctor_summary",
            ok=doctor_summary.get("ok", False),
            group_count=doctor_summary.get("group_count", 0),
            top_items=doctor_summary.get("top_items", []),
            groups=doctor_summary.get("groups", []),
            recommended_actions=doctor_summary.get("recommended_actions", []),
        )

        if result.get("ok"):
            log.info("🩺 [Doctor] 环境体检通过，可以继续执行。")
            final_status = "success"
            exit_code = 0
        else:
            final_error = "doctor 检查未通过"
            log.error("❌ [Doctor] 环境体检未通过，请先修复前置条件。")
            for check in result.get("checks", []):
                if not check.get("ok", False):
                    log.error(_build_doctor_check_failure_message(check))
            remediation_items = doctor_summary.get("recommended_actions", [])
            if remediation_items:
                log.error("🧭 [Doctor] 建议优先处理以下问题：")
                for index, item in enumerate(remediation_items, start=1):
                    log.error(f"   {index}. {item.get('message', '')}")
                    if item.get("fix_command"):
                        log.error(f"      命令: {item.get('fix_command', '')}")
                    if item.get("fix_doc"):
                        log.error(
                            "      文档: "
                            f"{item.get('fix_doc', '')} ({item.get('fix_doc_section', '')})"
                        )
    finally:
        reporter.finalize(
            status=final_status,
            exit_code=exit_code,
            steps_executed=len(result.get("checks", [])) if "result" in locals() else 0,
            last_error=final_error,
        )
    return exit_code


def run_capabilities_mode(args) -> int:
    payload = get_capabilities_payload()
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    sys.stdout.flush()
    return 0
