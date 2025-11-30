from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import List

router = APIRouter(prefix="/userprofiles", tags=["user profiles"])


class UserProfile(BaseModel):
	"""User profile type model."""
	profile_type: str
	description: str
	login_interface: str  # "user" or "sysadmin"


class UserProfilesResponse(BaseModel):
	"""Response model for user profiles list."""
	profiles: List[UserProfile]


@router.get("", response_model=UserProfilesResponse)
def get_user_profiles():
	"""
	Get available user profile types for login dropdown.
	
	Returns a list of user profile types that can be selected on the login page.
	FREE and PAID users share the same login interface, while SYSADMIN has a separate interface.
	"""
	try:
		profiles = [
			UserProfile(
				profile_type="FREE",
				description="Free account with limited storage",
				login_interface="user"
			),
			UserProfile(
				profile_type="PAID",
				description="Paid account with extended storage and features",
				login_interface="user"
			),
			UserProfile(
				profile_type="SYSADMIN",
				description="System administrator account",
				login_interface="sysadmin"
			),
		]
		
		return UserProfilesResponse(profiles=profiles)
		
	except Exception as e:
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=f"Error retrieving user profiles: {str(e)}",
		)


@router.get("/test-master-node")
async def test_master_node():
	"""Test master node connection."""
	try:
		from app.master_node_db import get_master_db
		master_db = get_master_db()
		
		# Test simple connection
		nodes = master_db.get_nodes()
		return {
			"status": "success",
			"message": "Master node connection working",
			"node_count": len(nodes),
			"nodes": nodes
		}
	except Exception as e:
		return {
			"status": "error", 
			"message": str(e),
			"master_url": "http://master_node:8000"
		}

