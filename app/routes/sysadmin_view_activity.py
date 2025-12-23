from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.master_node_db import MasterNodeDB, get_master_db

router = APIRouter(prefix="/sysadmin/activity", tags=["sysadmin"])


class SysadminActivity(BaseModel):
    activity_id: str
    account_id: str
    action_type: str
    resource_type: str
    resource_id: str
    ip_address: Optional[str]
    user_agent: Optional[str]
    details: Optional[str]
    created_at: str


def resolve_account_id(
    master_db: MasterNodeDB,
    account_id: Optional[str],
    username: Optional[str],
) -> Optional[str]:
    """
    Resolve account_id from either account_id or username.
    If both are None, return None (meaning no filter by user).
    """
    if account_id:
        return account_id

    if username:
        rows = master_db.select(
            "SELECT account_id FROM account WHERE username = $1",
            [username],
        )
        if not rows:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account with given username not found",
            )
        return str(rows[0]["account_id"])

    return None


@router.get("", response_model=List[SysadminActivity])
def list_activity(
    account_id: Optional[str] = Query(
        None,
        description="Filter by account_id; typically passed by frontend when clicking a user row",
    ),
    username: Optional[str] = Query(
        None,
        description="Optional filter by username (frontend can also use this for debugging)",
    ),
    action_type: Optional[str] = Query(
        None,
        description="Optional filter by action type (e.g. LOGIN, PASSWORDRESET, UPLOAD)",
    ),
    limit: int = Query(100, ge=1, le=1000),
    master_db: MasterNodeDB = Depends(get_master_db),
):
    """
    SysAdmin: View activity log.
    - Prefer account_id (frontend passes this when clicking a user row).
    - Alternatively, username can be used; backend resolves to account_id.
    - If neither is provided, returns recent activity across all users.
    """

    resolved_account_id = resolve_account_id(master_db, account_id, username)

    sql = """
        SELECT activity_id, account_id, action_type, resource_type, resource_id,
               ip_address, user_agent, details, created_at
        FROM activity_log
    """
    params: List[object] = []
    conditions: List[str] = []

    if resolved_account_id is not None:
        conditions.append("account_id = $1")
        params.append(resolved_account_id)

    if action_type is not None:
        placeholder_index = len(params) + 1
        conditions.append(f"action_type = ${placeholder_index}")
        params.append(action_type)

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    placeholder_index = len(params) + 1
    sql += f" ORDER BY created_at DESC LIMIT ${placeholder_index}"
    params.append(limit)

    try:
        rows = master_db.select(sql, params)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to load activity log: {str(e)}",
        )

    activities: List[SysadminActivity] = []
    for r in rows:
        created_at = r["created_at"]
        if isinstance(created_at, str):
            created_at_str = created_at
        else:
            created_at_str = (
                created_at.isoformat()
                if hasattr(created_at, "isoformat")
                else str(created_at)
            )

        activities.append(
            SysadminActivity(
                activity_id=str(r["activity_id"]),
                account_id=str(r["account_id"]),
                action_type=r["action_type"],
                resource_type=r["resource_type"],
                resource_id=str(r["resource_id"]),
                ip_address=r.get("ip_address"),
                user_agent=r.get("user_agent"),
                details=r.get("details"),
                created_at=created_at_str,
            )
        )

    return activities
