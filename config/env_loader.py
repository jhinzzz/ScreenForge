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


def safe_load_dotenv(dotenv_path: Path, override: bool = False) -> bool:
    # python-dotenv is a hard core dependency (pyproject.toml), so import it
    # directly — the old hand-rolled fallback parser could never run.
    from dotenv import load_dotenv

    return bool(load_dotenv(dotenv_path=dotenv_path, override=override))
