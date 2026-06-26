"""Multi-step session management for Claude Code integration.

A session groups multiple --action calls into one test file and one recording.
The recording process survives across CLI invocations via saved PID.
"""

import json
import os
import signal
import subprocess
import sys
import time

_SESSION_DIR = os.path.abspath(os.path.join("report", "sessions"))


def _session_file(session_id: str) -> str:
    return os.path.join(_SESSION_DIR, f"{session_id}.json")


def load_session(session_id: str) -> dict | None:
    path = _session_file(session_id)
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        return json.load(f)


def create_session(session_id: str, platform: str, output_path: str) -> dict:
    os.makedirs(_SESSION_DIR, exist_ok=True)
    session = {
        "session_id": session_id,
        "platform": platform,
        "output_path": output_path,
        "created_at": time.time(),
        "updated_at": time.time(),
        "steps": 0,
        "recording": False,
    }
    _save_session(session)
    return session


def update_session(session_id: str, **kwargs) -> dict:
    session = load_session(session_id)
    if not session:
        raise ValueError(f"Session not found: {session_id}")
    session.update(kwargs)
    session["updated_at"] = time.time()
    _save_session(session)
    return session


def delete_session(session_id: str) -> None:
    path = _session_file(session_id)
    if os.path.exists(path):
        os.remove(path)


def resolve_session_output_path(session_id: str, platform: str) -> str:
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    platform_dir = os.path.join(base_dir, "test_cases", platform)
    os.makedirs(platform_dir, exist_ok=True)
    return os.path.join(platform_dir, f"test_session_{session_id}.py")


def start_session_recording(session_id: str, platform: str, udid: str = "") -> str | None:
    if sys.platform != "darwin":
        return None
    if platform != "ios":
        return None
    if not udid:
        try:
            result = subprocess.run(
                ["xcrun", "simctl", "list", "devices", "booted", "-j"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                for runtime_devices in data.get("devices", {}).values():
                    for device in runtime_devices:
                        if device.get("state") == "Booted":
                            udid = device.get("udid", "")
                            break
                    if udid:
                        break
        except Exception:
            pass
    if not udid:
        return None

    video_dir = os.path.abspath("report")
    os.makedirs(video_dir, exist_ok=True)
    video_path = os.path.join(video_dir, f"session_{session_id}.mov")

    cmd = ["xcrun", "simctl", "io", udid, "recordVideo", video_path]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid,
    )
    time.sleep(1.0)
    if proc.poll() is not None:
        return None

    update_session(session_id, recording_pid=proc.pid, video_path=video_path)
    return video_path


def stop_session_recording(session_id: str) -> str:
    session = load_session(session_id)
    if not session:
        return ""
    pid = session.get("recording_pid")
    video_path = session.get("video_path", "")
    if not pid:
        return ""

    try:
        pgid = os.getpgid(pid)
        os.killpg(pgid, signal.SIGINT)
        os.waitpid(pid, 0)
    except OSError:
        try:
            os.kill(pid, signal.SIGINT)
            time.sleep(2)
        except OSError:
            pass

    if video_path and os.path.exists(video_path):
        size = os.path.getsize(video_path)
        if size > 1024:
            return video_path
    return ""


def _save_session(session: dict) -> None:
    os.makedirs(_SESSION_DIR, exist_ok=True)
    path = _session_file(session["session_id"])
    with open(path, "w") as f:
        json.dump(session, f)
