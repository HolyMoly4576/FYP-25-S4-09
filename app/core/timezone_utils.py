# app/core/timezone_utils.py
"""
Timezone utilities for handling local timezone operations.
Configures the application to use Singapore Standard Time (UTC+8).
"""
from datetime import datetime, timezone, timedelta
from typing import Optional
import os

# Singapore Standard Time (UTC+8)
SGT = timezone(timedelta(hours=8))

# You can change this to use different timezones or auto-detect system timezone
LOCAL_TIMEZONE = SGT

def get_local_timezone():
    """Get the configured local timezone for the application."""
    return LOCAL_TIMEZONE

def now_local():
    """Get current datetime in local timezone (Singapore Standard Time)."""
    return datetime.now(LOCAL_TIMEZONE)

def now_utc():
    """Get current datetime in UTC (for database storage compatibility)."""
    return datetime.now(timezone.utc)

def to_local_timezone(dt: datetime) -> datetime:
    """Convert a datetime to local timezone."""
    if dt.tzinfo is None:
        # Assume UTC if no timezone info
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(LOCAL_TIMEZONE)

def to_utc(dt: datetime) -> datetime:
    """Convert a datetime to UTC."""
    if dt.tzinfo is None:
        # Assume local timezone if no timezone info
        dt = dt.replace(tzinfo=LOCAL_TIMEZONE)
    return dt.astimezone(timezone.utc)

def format_local_datetime(dt: datetime, format_str: str = "%Y-%m-%d %H:%M:%S %Z") -> str:
    """Format datetime in local timezone."""
    local_dt = to_local_timezone(dt)
    return local_dt.strftime(format_str)

def parse_date_to_local_range(date_str: str):
    """
    Parse a date string (YYYY-MM-DD) and return start/end datetimes for the entire day
    in local timezone, then convert to UTC for database queries.
    """
    from datetime import datetime as dt
    
    # Parse date string (YYYY-MM-DD)
    filter_date = dt.strptime(date_str, "%Y-%m-%d").date()
    
    # Create datetime range for the entire day in local timezone
    start_datetime = dt.combine(filter_date, dt.min.time()).replace(tzinfo=LOCAL_TIMEZONE)
    end_datetime = dt.combine(filter_date, dt.max.time()).replace(tzinfo=LOCAL_TIMEZONE)
    
    # Convert to UTC for database queries (since database stores UTC)
    start_utc = start_datetime.astimezone(timezone.utc)
    end_utc = end_datetime.astimezone(timezone.utc)
    
    return start_utc, end_utc

# For backward compatibility and database operations
# We'll keep using UTC for database storage but display in local time
def get_display_timezone():
    """Get timezone for displaying to users."""
    return LOCAL_TIMEZONE

def get_storage_timezone():
    """Get timezone for database storage (keep as UTC for consistency)."""
    return timezone.utc