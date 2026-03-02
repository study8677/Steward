"""记忆系统 REST API——供 Dashboard 和大模型 Tool 调用。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from steward.services.memory_manager import MemoryManager

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])


def _get_memory(request: Request) -> MemoryManager:
    """从 app.state 获取 MemoryManager 实例。"""
    mgr = getattr(request.app.state, "memory_manager", None)
    if mgr is None:
        raise HTTPException(503, "MemoryManager not initialized")
    return mgr


class WriteRequest(BaseModel):
    """写入请求。"""

    subdir: str  # rules / projects / people / journal
    name: str  # 文件名前缀或关键词
    content: str


@router.get("/list")
async def list_files(request: Request, subdir: str = "") -> dict[str, object]:
    """列出记忆文件。"""
    mgr = _get_memory(request)
    files = mgr.list_files(subdir=subdir)
    return {"subdir": subdir, "files": files}


@router.get("/read")
async def read_file(request: Request, path: str = "") -> dict[str, str]:
    """读取指定记忆文件内容。"""
    mgr = _get_memory(request)
    if not path:
        raise HTTPException(400, "path parameter required")
    content = mgr.read_file(path)
    if not content:
        raise HTTPException(404, f"File not found: {path}")
    return {"path": path, "content": content}


@router.get("/search")
async def search_files(
    request: Request, keyword: str = "", subdir: str | None = None
) -> dict[str, object]:
    """搜索记忆文件中的关键词。"""
    mgr = _get_memory(request)
    if not keyword:
        raise HTTPException(400, "keyword parameter required")
    results = mgr.search(keyword=keyword, subdir=subdir)
    return {"keyword": keyword, "subdir": subdir, "results": results}


@router.post("/write")
async def write_file(request: Request, body: WriteRequest) -> dict[str, str]:
    """写入记忆文件。"""
    mgr = _get_memory(request)

    if body.subdir == "journal":
        path = mgr.write_journal(content=body.content)
    elif body.subdir == "rules":
        path = mgr.write_rule(name=body.name, content=body.content)
    elif body.subdir == "projects":
        path = mgr.write_project_memo(project=body.name, content=body.content)
    elif body.subdir == "people":
        path = mgr.write_person_memo(person=body.name, content=body.content)
    else:
        raise HTTPException(400, f"Unknown subdir: {body.subdir}")

    return {"status": "ok", "path": str(path)}
