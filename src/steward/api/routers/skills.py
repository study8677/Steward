"""技能管理 REST API——统一复用 IntegrationConfigService 状态。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from steward.api.deps import get_services
from steward.services.container import ServiceContainer

router = APIRouter(prefix="/api/v1/skills", tags=["skills"])


class InstallRequest(BaseModel):
    """安装请求。"""

    skill_id: str
    config_values: dict[str, str] | None = None
    run_install_command: bool = False


class ToggleRequest(BaseModel):
    """启用/禁用请求。"""

    skill_id: str
    enabled: bool


def _normalize_skill_record(raw: dict[str, object]) -> dict[str, object]:
    """将 Integration skill 状态映射为 catalog 响应项。"""
    skill_id = str(raw.get("skill", "")).strip()
    provider_type = str(raw.get("provider_type", "builtin") or "builtin")
    return {
        "id": skill_id,
        "name": str(raw.get("display_name", skill_id) or skill_id),
        "description": str(raw.get("description", "") or ""),
        "type": provider_type,
        "category": "general",
        "icon": "skill",
        "installed": bool(raw.get("installed", False)),
        "enabled": bool(raw.get("enabled", False)),
        "source": str(raw.get("source", "") or ""),
        "config_keys": [],
        "install_command": "",
        "install_note": "",
    }


@router.get("/catalog")
async def list_catalog(
    services: ServiceContainer = Depends(get_services),
) -> dict[str, object]:
    """返回完整技能目录（统一来源于 IntegrationConfigService）。"""
    statuses = services.integration_config_service.skill_status()
    return {"skills": [_normalize_skill_record(item) for item in statuses]}


@router.get("/installed")
async def list_installed(
    services: ServiceContainer = Depends(get_services),
) -> dict[str, object]:
    """返回已启用或本机已安装的技能。"""
    statuses = services.integration_config_service.skill_status()
    installed: list[dict[str, object]] = []
    for item in statuses:
        enabled = bool(item.get("enabled", False))
        local_installed = bool(item.get("installed", False))
        if not enabled and not local_installed:
            continue
        installed.append(
            {
                "skill_id": str(item.get("skill", "")).strip(),
                "enabled": enabled,
                "installed": local_installed,
                "source": str(item.get("source", "") or ""),
            }
        )
    return {"installed": installed}


@router.post("/install")
async def install_skill(
    body: InstallRequest,
    services: ServiceContainer = Depends(get_services),
) -> dict[str, str]:
    """兼容旧接口：将技能标记为启用并保存配置。"""
    payload: dict[str, object] = {"enabled": True}
    if body.config_values:
        payload["config_values"] = body.config_values

    result = services.integration_config_service.configure_skill(
        skill=body.skill_id,
        payload=payload,
    )
    skill = str(result.get("skill", "")).strip()
    if not skill:
        raise HTTPException(status_code=400, detail="invalid_skill")

    message = f"技能 {skill} 已启用"
    if body.run_install_command:
        message = f"{message}（已忽略 run_install_command，需手动安装依赖）"
    return {"status": "ok", "message": message}


@router.post("/uninstall")
async def uninstall_skill(
    body: InstallRequest,
    services: ServiceContainer = Depends(get_services),
) -> dict[str, str]:
    """兼容旧接口：将技能标记为停用。"""
    if not services.integration_config_service.has_skill(body.skill_id):
        raise HTTPException(status_code=400, detail=f"技能未找到: {body.skill_id}")
    status = services.integration_config_service.set_skill_enabled(body.skill_id, False)
    if status is None:
        raise HTTPException(status_code=400, detail="invalid_skill")
    return {"status": "ok", "message": f"技能 {body.skill_id} 已停用"}


@router.post("/toggle")
async def toggle_skill(
    body: ToggleRequest,
    services: ServiceContainer = Depends(get_services),
) -> dict[str, str]:
    """启用/禁用一个技能。"""
    if not services.integration_config_service.has_skill(body.skill_id):
        raise HTTPException(status_code=400, detail=f"技能未找到: {body.skill_id}")
    status = services.integration_config_service.set_skill_enabled(body.skill_id, body.enabled)
    if status is None:
        raise HTTPException(status_code=400, detail="invalid_skill")
    action = "启用" if body.enabled else "停用"
    return {"status": "ok", "message": f"技能 {body.skill_id} 已{action}"}
