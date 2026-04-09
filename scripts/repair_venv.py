import argparse
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from common.logs import log
from common.preflight import check_virtualenv_consistency, repair_virtualenv_consistency


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="修复当前项目 .venv 入口脚本漂移问题。")
    parser.add_argument(
        "--project-root",
        type=str,
        default=".",
        help="项目根目录",
    )
    return parser


def main():
    args = build_parser().parse_args()
    root = Path(args.project_root).resolve()
    current = check_virtualenv_consistency(root)
    if current.get("ok", False):
        log.info("✅ 当前 .venv 入口脚本已一致，无需修复。")
        return 0

    log.warning("⚠️ 检测到 .venv 存在入口漂移，开始修复...")
    for issue in current.get("issues", []):
        log.warning(f"   - {issue}")

    result = repair_virtualenv_consistency(root)
    verified = check_virtualenv_consistency(root)

    if not verified.get("ok", False):
        log.error("❌ .venv 修复后仍存在漂移，请人工检查。")
        for issue in verified.get("issues", []):
            log.error(f"   - {issue}")
        return 1

    updated_scripts = result.get("updated_scripts", [])
    if updated_scripts:
        log.info(f"✅ 已修复 {len(updated_scripts)} 个入口脚本。")
        for name in updated_scripts:
            log.info(f"   - {name}")
    if result.get("updated_pyvenv_cfg", False):
        log.info("✅ 已同步更新 pyvenv.cfg 中的创建命令路径。")
    log.info("🎯 当前项目已统一到本地 .venv 入口。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
