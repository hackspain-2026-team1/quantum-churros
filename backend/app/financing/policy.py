from dataclasses import dataclass

from fastapi import Header, HTTPException

ROLES = {"company", "consultant", "provider", "rumbo"}


@dataclass(frozen=True)
class Principal:
    user_id: str
    organization_id: str
    role: str


def current_principal(
    user_id: str | None = Header(default=None, alias="X-Rumbo-User"),
    organization_id: str | None = Header(default=None, alias="X-Rumbo-Organization"),
    role: str | None = Header(default=None, alias="X-Rumbo-Role"),
) -> Principal:
    if not user_id or not organization_id or role not in ROLES:
        raise HTTPException(status_code=401, detail="Rumbo identity headers are required")
    return Principal(user_id=user_id, organization_id=organization_id, role=role)


def require_role(principal: Principal, *roles: str) -> None:
    if principal.role not in roles:
        raise HTTPException(status_code=403, detail="Role cannot perform this action")
