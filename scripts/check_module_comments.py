#!/usr/bin/env python3
"""检查 Python 文件是否包含模块级注释（docstring）。"""

from __future__ import annotations

import ast
from pathlib import Path

SKIP_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
}


def iter_python_files(root: Path) -> list[Path]:
    """收集需要检查的 Python 文件。"""
    files: list[Path] = []
    for path in root.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        files.append(path)
    return sorted(files)


def has_module_docstring(path: Path) -> bool:
    """判断文件是否存在模块级 docstring。"""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    return bool(ast.get_docstring(tree))


def main() -> int:
    """执行检查并返回退出码。"""
    root = Path(__file__).resolve().parent.parent
    missing: list[Path] = []
    for file_path in iter_python_files(root):
        if not has_module_docstring(file_path):
            missing.append(file_path)

    if missing:
        print("以下文件缺少模块注释（docstring）：")
        for file_path in missing:
            print(f"- {file_path.relative_to(root)}")
        return 1

    print("所有 Python 文件均包含模块注释。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
