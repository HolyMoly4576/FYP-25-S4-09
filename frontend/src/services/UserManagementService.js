import { API_BASE_URL, authFetch } from "./UserService";

/**
 * Update profile (username and/or email)
 * Backend: PUT /user/profile
 * Body: { username?: string, email?: string }
 */
export async function updateProfile(payload) {
  const response = await authFetch(`${API_BASE_URL}/user/profile`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });

  // FastAPI returns JSON matching UpdateUserResponse
  const data = await response.json();
  return data;
}

/**
 * Update password
 * Backend: PUT /user/password
 * Body: { old_password: string, new_password: string }
 */
export async function updatePassword(payload) {
  const response = await authFetch(`${API_BASE_URL}/user/password`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });

  const data = await response.json();
  return data;
}

const UserManagementService = {
  updateProfile,
  updatePassword,
};

export default UserManagementService;