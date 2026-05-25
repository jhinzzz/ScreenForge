"""Bump version in cli/_version.py and pyproject.toml.

Usage: python scripts/bump_version.py 0.2.0
"""

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = PROJECT_ROOT / "cli" / "_version.py"
PYPROJECT_FILE = PROJECT_ROOT / "pyproject.toml"


def bump(new_version: str) -> None:
    # cli/_version.py
    VERSION_FILE.write_text(f'__version__ = "{new_version}"\n')

    # pyproject.toml
    content = PYPROJECT_FILE.read_text()
    content = re.sub(
        r'^version = ".*"$',
        f'version = "{new_version}"',
        content,
        count=1,
        flags=re.MULTILINE,
    )
    PYPROJECT_FILE.write_text(content)

    print(f"Bumped to {new_version}")
    print(f"  {VERSION_FILE}")
    print(f"  {PYPROJECT_FILE}")
    print("\nNext steps:")
    print("  git add cli/_version.py pyproject.toml")
    print(f'  git commit -m "chore: bump version to {new_version}"')
    print(f"  git tag v{new_version}")
    print("  git push origin main --tags")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <new_version>")
        sys.exit(1)
    bump(sys.argv[1])
