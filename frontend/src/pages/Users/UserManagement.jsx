import React, { useState } from "react";
import "../../styles/Users/UserManagement.css";
import UserManagementService from "../../services/UserManagementService";

const UserManagement = () => {
  // Profile form state
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");

  // Password form state
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");

  // Feedback state
  const [profileMessage, setProfileMessage] = useState("");
  const [profileError, setProfileError] = useState("");
  const [passwordMessage, setPasswordMessage] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [loadingProfile, setLoadingProfile] = useState(false);
  const [loadingPassword, setLoadingPassword] = useState(false);

  const handleProfileSubmit = async (e) => {
    e.preventDefault();
    setProfileMessage("");
    setProfileError("");

    // Build payload only with provided fields
    const payload = {};
    if (username.trim()) payload.username = username.trim();
    if (email.trim()) payload.email = email.trim();

    if (Object.keys(payload).length === 0) {
      setProfileError("Please provide at least a username or email to update.");
      return;
    }

    try {
      setLoadingProfile(true);
      const data = await UserManagementService.updateProfile(payload);
      // Backend returns UpdateUserResponse with message
      setProfileMessage(data.message || "Profile updated successfully.");
    } catch (err) {
      const detail =
        err?.response?.data?.detail ||
        "Failed to update profile. Please try again.";
      setProfileError(Array.isArray(detail) ? detail.join(", ") : detail);
    } finally {
      setLoadingProfile(false);
    }
  };

  const handlePasswordSubmit = async (e) => {
    e.preventDefault();
    setPasswordMessage("");
    setPasswordError("");

    if (!oldPassword || !newPassword) {
      setPasswordError("Both current and new password are required.");
      return;
    }

    try {
      setLoadingPassword(true);
      const payload = {
        old_password: oldPassword,
        new_password: newPassword,
      };
      const data = await UserManagementService.updatePassword(payload);
      setPasswordMessage(data.message || "Password updated successfully.");
      setOldPassword("");
      setNewPassword("");
    } catch (err) {
      const detail =
        err?.response?.data?.detail ||
        "Failed to update password. Please try again.";
      setPasswordError(Array.isArray(detail) ? detail.join(", ") : detail);
    } finally {
      setLoadingPassword(false);
    }
  };

  return (
    <div className="user-management-container">
      <h2>User Management</h2>

      <div className="user-management-grid">
        {/* Profile Update Card */}
        <div className="user-card">
          <h3>Update Profile</h3>
          <form onSubmit={handleProfileSubmit} className="user-form">
            <div className="form-group">
              <label htmlFor="username">New Username</label>
              <input
                id="username"
                type="text"
                placeholder="Enter new username (optional)"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="off"
              />
            </div>

            <div className="form-group">
              <label htmlFor="email">New Email</label>
              <input
                id="email"
                type="email"
                placeholder="Enter new email (optional)"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="off"
              />
            </div>

            {profileError && (
              <div className="form-feedback error">{profileError}</div>
            )}
            {profileMessage && (
              <div className="form-feedback success">{profileMessage}</div>
            )}

            <button
              type="submit"
              className="primary-btn"
              disabled={loadingProfile}
            >
              {loadingProfile ? "Updating..." : "Update Profile"}
            </button>
          </form>
        </div>

        {/* Password Update Card */}
        <div className="user-card">
          <h3>Change Password</h3>
          <form onSubmit={handlePasswordSubmit} className="user-form">
            <div className="form-group">
              <label htmlFor="oldPassword">Current Password</label>
              <input
                id="oldPassword"
                type="password"
                placeholder="Enter current password"
                value={oldPassword}
                onChange={(e) => setOldPassword(e.target.value)}
                autoComplete="current-password"
              />
            </div>

            <div className="form-group">
              <label htmlFor="newPassword">New Password</label>
              <input
                id="newPassword"
                type="password"
                placeholder="Enter new password (min 8 chars)"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                autoComplete="new-password"
              />
            </div>

            {passwordError && (
              <div className="form-feedback error">{passwordError}</div>
            )}
            {passwordMessage && (
              <div className="form-feedback success">{passwordMessage}</div>
            )}

            <button
              type="submit"
              className="primary-btn"
              disabled={loadingPassword}
            >
              {loadingPassword ? "Updating..." : "Change Password"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
};

export default UserManagement;