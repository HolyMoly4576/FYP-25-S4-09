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
	FREE and PAID users share the same login interface ("user"), while SYSADMIN has a separate interface ("sysadmin").
	The system automatically determines the actual account type (FREE/PAID) after login.
	"""
	try:
		profiles = [
			UserProfile(
				profile_type="USER",
				description="Regular user account (Free or Paid)",
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

