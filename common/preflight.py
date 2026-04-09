import importlib
import json
import subprocess
import shutil
import socket
from pathlib import Path
from typing import Dict, List
from urllib.parse import urlparse
from urllib.request import urlopen

import config.config as config
from utils.utils_web import normalize_loopback_url


def _resolve_venv_dir(project_root: Path) -> Path:
    project_root = Path(project_root).resolve()
    for candidate in [project_root, *project_root.parents]:
        venv_dir = candidate / ".venv"
        if venv_dir.exists():
            return venv_dir
    return project_root / ".venv"


def _iter_venv_entrypoints(bin_dir: Path):
    if not bin_dir.exists():
        return

    for path in sorted(bin_dir.iterdir()):
        if not path.is_file():
            continue
        try:
            with path.open("r", encoding="utf-8") as f:
                first_line = f.readline().strip()
        except (OSError, UnicodeDecodeError):
            continue
        if first_line.startswith("#!") and ".venv/bin/python" in first_line:
            yield path, first_line


def check_virtualenv_consistency(project_root: Path) -> Dict[str, object]:
    project_root = Path(project_root)
    venv_dir = _resolve_venv_dir(project_root)
    issues: List[str] = []
    checked_scripts: List[str] = []

    if not venv_dir.exists():
        return {
            "name": "venv_consistency",
            "ok": True,
            "venv_dir": str(venv_dir),
            "issues": issues,
            "checked_scripts": checked_scripts,
        }

    pyvenv_cfg = venv_dir / "pyvenv.cfg"
    if pyvenv_cfg.exists():
        for line in pyvenv_cfg.read_text(encoding="utf-8").splitlines():
            if line.startswith("command = ") and str(venv_dir) not in line and ".venv" in line:
                issues.append(f"pyvenv.cfg command 指向了其他环境: {line.split('=', 1)[1].strip()}")

    for path, shebang in _iter_venv_entrypoints(venv_dir / "bin"):
        checked_scripts.append(path.name)
        if str(venv_dir) not in shebang:
            issues.append(f"{path.name} shebang 指向了其他环境: {shebang[2:]}")

    return {
        "name": "venv_consistency",
        "ok": not issues,
        "venv_dir": str(venv_dir),
        "issues": issues,
        "checked_scripts": checked_scripts,
    }


def repair_virtualenv_consistency(project_root: Path) -> Dict[str, object]:
    project_root = Path(project_root)
    venv_dir = _resolve_venv_dir(project_root)
    bin_dir = venv_dir / "bin"
    expected_python = bin_dir / "python3.13"
    if not expected_python.exists():
        expected_python = bin_dir / "python"

    updated_scripts: List[str] = []
    if bin_dir.exists():
        for path, shebang in _iter_venv_entrypoints(bin_dir):
            if str(venv_dir) in shebang:
                continue

            original = path.read_text(encoding="utf-8")
            original_lines = original.splitlines()
            if not original_lines:
                continue
            original_lines[0] = f"#!{expected_python}"
            new_text = "\n".join(original_lines)
            if original.endswith("\n"):
                new_text += "\n"
            path.write_text(new_text, encoding="utf-8")
            updated_scripts.append(path.name)

    cfg_updated = False
    pyvenv_cfg = venv_dir / "pyvenv.cfg"
    if pyvenv_cfg.exists():
        new_lines = []
        for line in pyvenv_cfg.read_text(encoding="utf-8").splitlines():
            if line.startswith("command = ") and str(venv_dir) not in line and " -m venv " in line:
                command_prefix = line.split(" -m venv ", 1)[0].split("=", 1)[1].strip()
                line = f"command = {command_prefix} -m venv {venv_dir}"
                cfg_updated = True
            new_lines.append(line)
        pyvenv_cfg.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    return {
        "venv_dir": str(venv_dir),
        "updated_scripts": updated_scripts,
        "updated_pyvenv_cfg": cfg_updated,
    }


def check_required_config() -> Dict[str, object]:
    errors: List[str] = []

    if not config.OPENAI_API_KEY:
        errors.append("OPENAI_API_KEY 未配置")
    if config.DEFAULT_TIMEOUT <= 0:
        errors.append(f"DEFAULT_TIMEOUT 必须大于 0，当前值: {config.DEFAULT_TIMEOUT}")
    if not 0 <= config.CACHE_SIMILARITY_THRESHOLD <= 1:
        errors.append(
            f"CACHE_SIMILARITY_THRESHOLD 必须在 0-1 之间，当前值: {config.CACHE_SIMILARITY_THRESHOLD}"
        )
    if not 0 <= config.CACHE_EXACT_MATCH_THRESHOLD <= 1:
        errors.append(
            f"CACHE_EXACT_MATCH_THRESHOLD 必须在 0-1 之间，当前值: {config.CACHE_EXACT_MATCH_THRESHOLD}"
        )
    if not config.WEB_CDP_URL.startswith(("http://", "https://")):
        errors.append(
            f"WEB_CDP_URL 必须以 http:// 或 https:// 开头，当前值: {config.WEB_CDP_URL}"
        )

    return {
        "name": "config",
        "ok": not errors,
        "errors": errors,
    }


def check_module_import(module_name: str) -> Dict[str, object]:
    try:
        importlib.import_module(module_name)
        return {"name": module_name, "ok": True, "error": ""}
    except Exception as exc:
        return {"name": module_name, "ok": False, "error": str(exc)}


def check_runtime_paths(script_dir: Path, run_dir: Path) -> Dict[str, object]:
    script_dir = Path(script_dir)
    run_dir = Path(run_dir)
    script_dir.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)

    return {
        "name": "runtime_paths",
        "ok": script_dir.is_dir() and run_dir.is_dir(),
        "script_dir": str(script_dir),
        "run_dir": str(run_dir),
    }


def check_command_available(command_name: str) -> Dict[str, object]:
    command_path = shutil.which(command_name)
    return {
        "name": command_name,
        "ok": bool(command_path),
        "path": command_path or "",
        "hint": f"请确认 {command_name} 已安装并已加入 PATH。",
    }


def _is_environment_restricted_error(message: str) -> bool:
    text = str(message).lower()
    return any(
        pattern in text
        for pattern in (
            "operation not permitted",
            "permission denied",
            "smartsocket",
        )
    )


def check_tcp_endpoint(url: str, timeout_seconds: float = 1.0) -> Dict[str, object]:
    normalized_url = normalize_loopback_url(url)
    parsed = urlparse(normalized_url)
    host = parsed.hostname
    port = parsed.port
    if not host or not port:
        return {
            "name": url,
            "ok": False,
            "error": "无法从 URL 中解析 host 或 port",
            "hint": "请检查 URL 格式是否包含合法的 host 与 port。",
        }

    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return {"name": url, "ok": True, "error": "", "hint": ""}
    except OSError as exc:
        raw_error = str(exc)
        if _is_environment_restricted_error(raw_error):
            return {
                "name": url,
                "ok": False,
                "error": "当前运行环境限制了本地 TCP 连接检查",
                "raw_error": raw_error,
                "environment_restricted": True,
                "hint": (
                    f"请在宿主终端直接检查 {url}/json/version，"
                    "或在放宽本地网络权限后重试。"
                ),
            }
        return {
            "name": url,
            "ok": False,
            "error": raw_error,
            "hint": f"请确认 {url} 对应的本地服务已经启动。",
        }


def check_android_device_connected() -> Dict[str, object]:
    try:
        result = subprocess.run(
            ["adb", "devices"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception as exc:
        return {
            "name": "adb_devices",
            "ok": False,
            "devices": [],
            "blocked_devices": [],
            "error": str(exc),
            "hint": "请确认 adb 可执行，并且终端可以直接运行 `adb devices`。",
        }

    if result.returncode != 0:
        raw_error = result.stderr.strip() or result.stdout.strip() or "adb devices 执行失败"
        if _is_environment_restricted_error(raw_error):
            return {
                "name": "adb_devices",
                "ok": False,
                "devices": [],
                "blocked_devices": [],
                "error": "当前运行环境限制了 adb daemon 的本地端口监听",
                "raw_error": raw_error,
                "environment_restricted": True,
                "hint": "请在宿主终端直接执行 `adb devices`，或在放宽本地网络权限后重试。",
            }
        return {
            "name": "adb_devices",
            "ok": False,
            "devices": [],
            "blocked_devices": [],
            "error": raw_error,
            "hint": "请确认 adb 服务正常，并重新执行 `adb devices` 检查。",
        }

    devices = []
    blocked_devices = []
    for raw_line in result.stdout.splitlines()[1:]:
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split()
        serial = parts[0]
        status = parts[1] if len(parts) > 1 else "unknown"
        if status == "device":
            devices.append(serial)
        else:
            blocked_devices.append({"serial": serial, "status": status})

    if devices:
        return {
            "name": "adb_devices",
            "ok": True,
            "devices": devices,
            "blocked_devices": blocked_devices,
            "error": "",
            "hint": "",
        }

    if blocked_devices:
        blocked_desc = ", ".join(
            f"{item['serial']}({item['status']})" for item in blocked_devices
        )
        error = f"检测到 Android 设备但状态不可用: {blocked_desc}"
    else:
        error = "未检测到可用 Android 设备"

    return {
        "name": "adb_devices",
        "ok": False,
        "devices": [],
        "blocked_devices": blocked_devices,
        "error": error,
        "hint": "请连接设备、开启 USB 调试，并在手机上确认调试授权后重试。",
    }


def check_cdp_debug_endpoint(url: str, timeout_seconds: float = 1.5) -> Dict[str, object]:
    base_url = normalize_loopback_url(url).rstrip("/")
    version_url = f"{base_url}/json/version"
    try:
        with urlopen(version_url, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raw_error = str(exc)
        if _is_environment_restricted_error(raw_error):
            return {
                "name": "cdp_debug_endpoint",
                "ok": False,
                "browser": "",
                "websocket_url": "",
                "error": "当前运行环境限制了本地 HTTP 调试端点检查",
                "raw_error": raw_error,
                "environment_restricted": True,
                "hint": (
                    f"请在宿主终端直接检查 {version_url}，"
                    "或在放宽本地网络权限后重试。"
                ),
            }
        return {
            "name": "cdp_debug_endpoint",
            "ok": False,
            "browser": "",
            "websocket_url": "",
            "error": raw_error,
            "hint": "请以 `--remote-debugging-port=9222` 启动 Chrome，并确认 CDP 地址可访问。",
        }

    websocket_url = payload.get("webSocketDebuggerUrl", "")
    if not websocket_url:
        return {
            "name": "cdp_debug_endpoint",
            "ok": False,
            "browser": payload.get("Browser", ""),
            "websocket_url": "",
            "error": "CDP 元数据缺少 webSocketDebuggerUrl",
            "hint": "请确认当前端口暴露的是 Chrome DevTools Protocol，而不是普通 HTTP 服务。",
        }

    return {
        "name": "cdp_debug_endpoint",
        "ok": True,
        "browser": payload.get("Browser", ""),
        "websocket_url": websocket_url,
        "error": "",
        "hint": "",
    }


def check_wda_status_endpoint(url: str, timeout_seconds: float = 1.5) -> Dict[str, object]:
    status_url = f"{url.rstrip('/')}/status"
    try:
        with urlopen(status_url, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return {
            "name": "wda_status",
            "ok": False,
            "platform_name": "",
            "platform_version": "",
            "message": "",
            "error": str(exc),
            "hint": "请确认 WebDriverAgent 已在 iPhone 上启动，并且 8100 端口映射可用。",
        }

    value = payload.get("value")
    if not isinstance(value, dict):
        return {
            "name": "wda_status",
            "ok": False,
            "platform_name": "",
            "platform_version": "",
            "message": "",
            "error": "WDA status 响应缺少 value 字段",
            "hint": "请确认当前 8100 端口暴露的是有效的 WebDriverAgent status 接口。",
        }

    state = str(value.get("state", "")).strip()
    if state.lower() != "success":
        return {
            "name": "wda_status",
            "ok": False,
            "platform_name": "",
            "platform_version": "",
            "message": str(value.get("message", "")).strip(),
            "error": f"WDA 当前状态异常: {state or 'unknown'}",
            "hint": "请检查 WebDriverAgent 是否成功安装、签名，并确认真机已信任开发者证书。",
        }

    os_info = value.get("os", {}) if isinstance(value.get("os"), dict) else {}
    return {
        "name": "wda_status",
        "ok": True,
        "platform_name": str(os_info.get("name", "")).strip(),
        "platform_version": str(os_info.get("version", "")).strip(),
        "message": str(value.get("message", "")).strip(),
        "error": "",
        "hint": "",
    }


def run_preflight(platform: str, script_dir: Path, run_dir: Path) -> Dict[str, object]:
    checks = [
        check_required_config(),
        check_runtime_paths(script_dir, run_dir),
        check_virtualenv_consistency(config.BASE_DIR),
    ]

    if platform == "android":
        checks.append(check_module_import("uiautomator2"))
        checks.append(check_command_available("adb"))
        checks.append(check_android_device_connected())
    elif platform == "ios":
        checks.append(check_module_import("wda"))
        ios_endpoint_check = check_tcp_endpoint("http://localhost:8100")
        checks.append(ios_endpoint_check)
        if ios_endpoint_check.get("ok", False):
            checks.append(check_wda_status_endpoint("http://localhost:8100"))
    elif platform == "web":
        checks.append(check_module_import("playwright"))
        web_endpoint_check = check_tcp_endpoint(config.WEB_CDP_URL)
        checks.append(web_endpoint_check)
        if web_endpoint_check.get("ok", False):
            checks.append(check_cdp_debug_endpoint(config.WEB_CDP_URL))

    ok = all(item.get("ok", False) for item in checks)
    return {
        "ok": ok,
        "platform": platform,
        "checks": checks,
    }
