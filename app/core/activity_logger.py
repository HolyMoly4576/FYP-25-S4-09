"""
Activity logging utility for audit trail.
Logs user activities for security and compliance purposes.
"""
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import logging

from app.models import ActivityLog
import uuid

logger = logging.getLogger(__name__)


def log_activity(
    db: Session,
    account_id: uuid.UUID,
    action_type: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[uuid.UUID] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
):
    """
    Log an activity to the activity log.
    
    Args:
        db: Database session
        account_id: ID of the account performing the action
        action_type: Type of action (e.g., 'LOGIN', 'FILE_UPLOAD', 'FOLDER_DELETE')
        resource_type: Type of resource affected (e.g., 'FILE', 'FOLDER', 'ACCOUNT')
        resource_id: ID of the resource affected
        ip_address: IP address of the user
        user_agent: User agent string from request
        details: Additional context as dictionary (will be stored as JSONB)
    
    Returns:
        ActivityLog object or None if logging fails
    """
    try:
        activity = ActivityLog(
            account_id=account_id,
            action_type=action_type,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details
        )
        db.add(activity)
        db.commit()
        db.refresh(activity)
        return activity
    except Exception as e:
        db.rollback()
        logger.error(f"Error logging activity: {str(e)}")
        # Don't raise exception - logging failure shouldn't break the main operation
        return None


def get_client_ip(request) -> Optional[str]:
    """
    Extract client IP address from FastAPI request.
    Handles proxies and forwarded headers.
    """
    if not request:
        return None
    
    # Check for forwarded IP (from proxy/load balancer)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # X-Forwarded-For can contain multiple IPs, take the first one
        return forwarded_for.split(",")[0].strip()
    
    # Check for real IP header
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    
    # Fallback to direct client IP
    if hasattr(request, "client") and request.client:
        return request.client.host
    
    return None


def get_user_agent(request) -> Optional[str]:
    """Extract user agent from FastAPI request."""
    if not request:
        return None
    return request.headers.get("User-Agent")

