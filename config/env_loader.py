import os
import shlex
from pathlib import Path


def resolve_dotenv_path(project_root: Path):
    project_root = Path(project_root).resolve()
    for candidate_root in [project_root, *project_root.parents]:
        try:
            entries = {path.name.lower(): path for path in candidate_root.iterdir()}
        except OSError:
            continue
        for file_name in (".env", ".ENV"):
            candidate = entries.get(file_name.lower())
            if candidate and candidate.is_file():
                return candidate
    return project_root / ".env"


def _parse_env_line(line: str):
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    if line.startswith("export "):
        line = line[len("export ") :].strip()

    if "=" not in line:
        return None

    key, value = line.split("=", 1)
    key = key.strip()
    value = value.strip()
    if not key:
        return None

    if value and value[0] in {"'", '"'}:
        try:
            parsed = shlex.split(f"v={value}", posix=True)
            value = parsed[0].split("=", 1)[1] if parsed else ""
        except ValueError:
            if len(value) >= 2 and value[0] == value[-1]:
                value = value[1:-1]
    else:
        value = value.split(" #", 1)[0].rstrip()

    return key, value


def _fallback_load_dotenv(dotenv_path: Path, override: bool = False) -> bool:
    dotenv_path = Path(dotenv_path)
    if not dotenv_path.exists():
        return False

    loaded = False
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        parsed = _parse_env_line(raw_line)
        if not parsed:
            continue

        key, value = parsed
        loaded = True
        if key in os.environ and not override:
            continue
        os.environ[key] = value

    return loaded


def safe_load_dotenv(dotenv_path: Path, override: bool = False) -> bool:
    try:
        from dotenv import load_dotenv

        return bool(load_dotenv(dotenv_path=dotenv_path, override=override))
    except ModuleNotFoundError:
        return _fallback_load_dotenv(dotenv_path, override=override)
