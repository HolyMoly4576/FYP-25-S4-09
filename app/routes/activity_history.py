from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date, timezone
import logging

from app.db.session import get_db
from app.models import Account, ActivityLog
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
    db: Session = Depends(get_db)
) -> Account:
    """Get the current authenticated account."""
    token_str = token.credentials if hasattr(token, "credentials") else token
    payload = decode_access_token(token_str)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    account_id = payload.get("sub")
    if not account_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    account = db.query(Account).filter(Account.account_id == account_id).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return account


@router.get("/history", response_model=ActivityHistoryResponse)
def get_activity_history(
    date_filter: Optional[str] = Query(None, description="Filter by date (YYYY-MM-DD format). If not provided, shows all activities."),
    action_type: Optional[str] = Query(None, description="Filter by action type (e.g., 'LOGIN', 'FILE_UPLOAD')"),
    limit: int = Query(50, ge=1, le=200, description="Number of activities to return"),
    offset: int = Query(0, ge=0, description="Number of activities to skip"),
    current_account: Account = Depends(get_current_account),
    db: Session = Depends(get_db)
):
    """
    Get activity history for the current authenticated user.
    Supports filtering by date and action type.
    """
    try:
        # Base query - only activities for current user
        query = db.query(ActivityLog).filter(
            ActivityLog.account_id == current_account.account_id
        )
        
        # Apply date filter if provided
        if date_filter:
            try:
                # Parse date string (YYYY-MM-DD)
                filter_date = datetime.strptime(date_filter, "%Y-%m-%d").date()
                # Create datetime range for the entire day (00:00:00 to 23:59:59)
                start_datetime = datetime.combine(filter_date, datetime.min.time()).replace(tzinfo=timezone.utc)
                end_datetime = datetime.combine(filter_date, datetime.max.time()).replace(tzinfo=timezone.utc)
                
                query = query.filter(
                    and_(
                        ActivityLog.created_at >= start_datetime,
                        ActivityLog.created_at <= end_datetime
                    )
                )
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid date format. Use YYYY-MM-DD (e.g., 2025-11-15)"
                )
        
        # Apply action type filter if provided
        if action_type:
            query = query.filter(ActivityLog.action_type == action_type.upper())
        
        # Get total count before pagination
        total = query.count()
        
        # Apply pagination and ordering (newest first)
        activities = query.order_by(ActivityLog.created_at.desc()).offset(offset).limit(limit).all()
        
        # Convert to response format
        activity_list = []
        for activity in activities:
            activity_list.append(ActivityDetail(
                activity_id=str(activity.activity_id),
                action_type=activity.action_type,
                resource_type=activity.resource_type,
                resource_id=str(activity.resource_id) if activity.resource_id else None,
                ip_address=activity.ip_address,
                user_agent=activity.user_agent,
                details=activity.details if activity.details else None,
                created_at=activity.created_at.isoformat()
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

