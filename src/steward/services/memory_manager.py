"""Markdown 记忆管理器——管理 ~/.steward_brain/ 目录下的规则与记忆文件。"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import structlog

logger = structlog.get_logger("memory_manager")

# 子目录定义
SUBDIRS = ("rules", "projects", "people", "journal")


class MemoryManager:
    """管理 ~/.steward_brain/ 目录下的 Markdown 记忆文件。

    设计原则：
    - 不使用 RAG / 向量检索；大模型通过 bash 命令（ls/cat/grep）主动查找
    - 严格的文件夹结构与命名契约
    - 对用户完全透明，可随时手工编辑
    """

    def __init__(self, brain_dir: str = "~/.steward_brain") -> None:
        self._brain_dir = Path(brain_dir).expanduser().resolve()

    @property
    def brain_dir(self) -> Path:
        """返回记忆根目录。"""
        return self._brain_dir

    # ── 初始化 ──────────────────────────────────────────

    def ensure_structure(self) -> None:
        """首次启动时创建目录结构。"""
        for sub in SUBDIRS:
            (self._brain_dir / sub).mkdir(parents=True, exist_ok=True)

        readme = self._brain_dir / "README.md"
        if not readme.exists():
            readme.write_text(
                "# Steward Brain\n\n"
                "此目录由 Steward Agent 自动管理。\n"
                "你可以随时手动编辑任何 `.md` 文件，Agent 下次读取时会自动对齐。\n\n"
                "## 目录结构\n\n"
                "- `rules/` — 持久规则（偏好、分类策略等）\n"
                "- `projects/` — 按项目维度的记忆\n"
                "- `people/` — 按人物维度的记忆\n"
                "- `journal/` — 按日期的事件日志\n",
                encoding="utf-8",
            )
        logger.info("brain_structure_ensured", path=str(self._brain_dir))

    # ── 写入 ──────────────────────────────────────────

    def write_journal(self, content: str, date: str | None = None) -> Path:
        """追加当日日志。"""
        if not date:
            date = datetime.now(UTC).strftime("%Y%m%d")
        filepath = self._brain_dir / "journal" / f"{date}.md"
        timestamp = datetime.now(UTC).strftime("%H:%M:%S")

        if filepath.exists():
            with filepath.open("a", encoding="utf-8") as f:
                f.write(f"\n---\n\n### {timestamp}\n\n{content}\n")
        else:
            filepath.write_text(
                f"# 日志 {date}\n\n### {timestamp}\n\n{content}\n",
                encoding="utf-8",
            )

        logger.info("journal_written", date=date)
        return filepath

    def write_rule(self, name: str, content: str) -> Path:
        """创建或覆盖规则文件。"""
        safe_name = self._sanitize_name(name)
        filepath = self._brain_dir / "rules" / f"rule_{safe_name}.md"
        filepath.write_text(
            f"# 规则: {name}\n\n{content}\n",
            encoding="utf-8",
        )
        logger.info("rule_written", name=safe_name)
        return filepath

    def write_project_memo(self, project: str, content: str, month: str | None = None) -> Path:
        """创建或追加项目记忆。"""
        if not month:
            month = datetime.now(UTC).strftime("%Y%m")
        safe_name = self._sanitize_name(project)
        filepath = self._brain_dir / "projects" / f"proj_{safe_name}_{month}.md"

        if filepath.exists():
            with filepath.open("a", encoding="utf-8") as f:
                f.write(f"\n---\n\n{content}\n")
        else:
            filepath.write_text(
                f"# 项目: {project} ({month})\n\n{content}\n",
                encoding="utf-8",
            )

        logger.info("project_memo_written", project=safe_name, month=month)
        return filepath

    def write_person_memo(self, person: str, content: str) -> Path:
        """创建或追加人物记忆。"""
        safe_name = self._sanitize_name(person)
        filepath = self._brain_dir / "people" / f"person_{safe_name}.md"

        if filepath.exists():
            with filepath.open("a", encoding="utf-8") as f:
                f.write(f"\n---\n\n{content}\n")
        else:
            filepath.write_text(
                f"# 人物: {person}\n\n{content}\n",
                encoding="utf-8",
            )

        logger.info("person_memo_written", person=safe_name)
        return filepath

    # ── 读取 ──────────────────────────────────────────

    def list_files(self, subdir: str = "", pattern: str = "*.md") -> list[dict[str, str]]:
        """列出指定子目录下的文件。"""
        base = self._brain_dir / subdir if subdir else self._brain_dir
        if not base.exists():
            return []

        files = sorted(base.glob(pattern))
        return [
            {
                "name": f.name,
                "path": str(f.relative_to(self._brain_dir)),
                "size": str(f.stat().st_size),
            }
            for f in files
            if f.is_file()
        ]

    def read_file(self, relative_path: str) -> str:
        """读取文件内容（相对于 brain_dir）。"""
        filepath = self._brain_dir / relative_path
        if not filepath.exists() or not filepath.is_file():
            return ""
        # 安全检查：不允许路径穿越
        try:
            filepath.resolve().relative_to(self._brain_dir)
        except ValueError:
            return ""
        return filepath.read_text(encoding="utf-8")

    def search(self, keyword: str, subdir: str | None = None) -> list[dict[str, str]]:
        """在指定范围内搜索关键词，返回匹配结果。"""
        base = self._brain_dir / subdir if subdir else self._brain_dir
        if not base.exists():
            return []

        results: list[dict[str, str]] = []
        for md_file in sorted(base.rglob("*.md")):
            if not md_file.is_file():
                continue
            try:
                content = md_file.read_text(encoding="utf-8")
            except OSError:
                continue
            for i, line in enumerate(content.splitlines(), 1):
                if keyword.lower() in line.lower():
                    results.append(
                        {
                            "file": str(md_file.relative_to(self._brain_dir)),
                            "line": str(i),
                            "content": line.strip()[:120],
                        }
                    )
                    if len(results) >= 50:
                        return results

        return results

    # ── 工具 ──────────────────────────────────────────

    @staticmethod
    def _sanitize_name(name: str) -> str:
        """将名称转为安全的文件名片段。"""
        safe = re.sub(r"[^\w\u4e00-\u9fff-]", "_", name.strip().lower())
        return safe[:60] or "unnamed"
