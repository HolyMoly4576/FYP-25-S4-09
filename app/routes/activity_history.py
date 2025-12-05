from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date, timezone
import logging
import json

from app.master_node_db import MasterNodeDB, get_master_db
from app.core.security import decode_access_token
from app.routes.login import oauth2_scheme

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/activity", tags=["activity"])


class ActivityDetail(BaseModel):
    activity_id: str
    action_type: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    details: Optional[dict] = None
    created_at: str


class ActivityHistoryResponse(BaseModel):
    activities: List[ActivityDetail]
    total: int
    limit: int
    offset: int
    date_filter: Optional[str] = None


def get_current_account(
    token=Depends(oauth2_scheme),
    master_db: MasterNodeDB = Depends(get_master_db)
) -> dict:
    """Get the current authenticated account from master node."""
    token_str = token.credentials if hasattr(token, "credentials") else token
    payload = decode_access_token(token_str)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    
    account_id = payload.get("sub")
    if not account_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    
    account_result = master_db.select(
        "SELECT account_id, username, email, account_type, created_at FROM account WHERE account_id = $1",
        [account_id]
    )
    
    if not account_result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    return account_result[0]


@router.get("/history", response_model=ActivityHistoryResponse)
def get_activity_history(
    date_filter: Optional[str] = Query(None, description="Filter by date (YYYY-MM-DD format). If not provided, shows all activities."),
    action_type: Optional[str] = Query(None, description="Filter by action type (e.g., 'LOGIN', 'FILE_UPLOAD')"),
    limit: int = Query(50, ge=1, le=200, description="Number of activities to return"),
    offset: int = Query(0, ge=0, description="Number of activities to skip"),
    current_account: dict = Depends(get_current_account),
    master_db: MasterNodeDB = Depends(get_master_db)
):
    """
    Get activity history for the current authenticated user.
    Supports filtering by date and action type.
    """
    try:
        # Build SQL query with filters
        sql_conditions = ["account_id = $1"]
        params = [current_account["account_id"]]
        param_index = 2
        
        # Apply date filter if provided
        start_datetime = None
        end_datetime = None
        if date_filter:
            try:
                # Parse date string (YYYY-MM-DD)
                filter_date = datetime.strptime(date_filter, "%Y-%m-%d").date()
                # Create datetime range for the entire day (00:00:00 to 23:59:59)
                start_datetime = datetime.combine(filter_date, datetime.min.time()).replace(tzinfo=timezone.utc)
                end_datetime = datetime.combine(filter_date, datetime.max.time()).replace(tzinfo=timezone.utc)
                
                sql_conditions.append(f"created_at >= ${param_index}")
                params.append(start_datetime)
                param_index += 1
                
                sql_conditions.append(f"created_at <= ${param_index}")
                params.append(end_datetime)
                param_index += 1
                
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid date format. Use YYYY-MM-DD (e.g., 2025-11-15)"
                )
        
        # Apply action type filter if provided
        if action_type:
            sql_conditions.append(f"action_type = ${param_index}")
            params.append(action_type.upper())
            param_index += 1
        
        # Build WHERE clause
        where_clause = " AND ".join(sql_conditions)
        
        # Get total count via master node
        count_sql = f"SELECT COUNT(*) as total FROM activity_log WHERE {where_clause}"
        count_result = master_db.select(count_sql, params)
        total = int(count_result[0]["total"]) if count_result else 0
        
        # Get activities with pagination via master node
        activities_sql = f"""
            SELECT activity_id, action_type, resource_type, resource_id, ip_address, user_agent, details, created_at
            FROM activity_log
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_index} OFFSET ${param_index + 1}
        """
        params.extend([limit, offset])
        
        activities = master_db.select(activities_sql, params)
        
        # Convert to response format
        activity_list = []
        for activity in activities:
            # Handle details field (might be JSON or dict)
            details_value = activity.get("details")
            if isinstance(details_value, str):
                import json
                try:
                    details_value = json.loads(details_value)
                except:
                    details_value = None
            
            # Format created_at
            created_at = activity["created_at"]
            if hasattr(created_at, "isoformat"):
                created_at_str = created_at.isoformat()
            else:
                created_at_str = str(created_at)
            
            activity_list.append(ActivityDetail(
                activity_id=str(activity["activity_id"]),
                action_type=activity["action_type"],
                resource_type=activity.get("resource_type"),
                resource_id=str(activity["resource_id"]) if activity.get("resource_id") else None,
                ip_address=activity.get("ip_address"),
                user_agent=activity.get("user_agent"),
                details=details_value,
                created_at=created_at_str
            ))
        
        return ActivityHistoryResponse(
            activities=activity_list,
            total=total,
            limit=limit,
            offset=offset,
            date_filter=date_filter
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving activity history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving activity history: {str(e)}"
        )