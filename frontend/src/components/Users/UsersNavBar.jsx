import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import ShardLogo from "../Shard_Logo.png";
import { getCurrentUser, clearAuth } from "../../services/UserService";
import "../../styles/Users/UsersNavBar.css";

const UsersNavBar = ({ storageUsage, loadingUsage, usageError }) => {
  const navigate = useNavigate();
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);

  const user = getCurrentUser();
  const username = user?.username || "User";

  const handleLogout = () => {
    clearAuth();
    navigate("/"); // HomePage route
  };

  const toggleDropdown = () => {
    setIsDropdownOpen((prev) => !prev);
  };

  return (
    <div className="users-layout">
      {/* Left sidebar */}
      <aside className="users-sidebar">
        <div className="sidebar-logo">
          <img src={ShardLogo} alt="Shard Logo" />
        </div>

        <nav className="sidebar-nav">
          <Link to="/dashboard/files" className="sidebar-link">
            All Files
          </Link>
          <Link to="/dashboard/shared" className="sidebar-link">
            Shared
          </Link>
          <Link to="/dashboard/activity" className="sidebar-link">
            Activity History
          </Link>
        </nav>

        <div className="sidebar-storage">
          <span className="storage-label">Storage Usage</span>
          {loadingUsage && (
            <span className="storage-value">Loading...</span>
          )}
          {!loadingUsage && usageError && (
            <span className="storage-value">Error</span>
          )}
          {!loadingUsage && !usageError && storageUsage && (
            <span className="storage-value">
              {storageUsage.percentUsed}% used
            </span>
          )}
        </div>
      </aside>

      {/* Top header bar */}
      <header className="users-header">
        <div className="header-left" />

        <div className="header-right">
          <div className="user-dropdown-wrapper">
            <button
              className="user-dropdown-toggle"
              onClick={toggleDropdown}
            >
              Welcome, {username}
            </button>
            {isDropdownOpen && (
              <div className="user-dropdown-menu">
                <Link
                  to="/user-management"
                  className="user-dropdown-item"
                  onClick={() => setIsDropdownOpen(false)}
                >
                  User Management
                </Link>
                <Link
                  to="/account-management"
                  className="user-dropdown-item"
                  onClick={() => setIsDropdownOpen(false)}
                >
                  Account Management
                </Link>
              </div>
            )}
          </div>

          <button className="logout-button" onClick={handleLogout}>
            Logout
          </button>
        </div>
      </header>

      {/* Main content area placeholder */}
      <main className="users-main-content">
        {/* Your routed content (e.g. <Outlet /> or props.children) */}
      </main>
    </div>
  );
};

export default UsersNavBar;
