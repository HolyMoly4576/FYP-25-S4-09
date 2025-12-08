import React, { useState } from "react";
import { NavLink } from "react-router-dom";
import { Link, useNavigate } from "react-router-dom";
import ShardLogo from "../Shard_Logo.png";
import { getCurrentUser, clearAuth } from "../../services/UserService";
import "../../styles/Users/UsersNavBar.css";

const UsersNavBar = ({ storageUsage, loadingUsage, usageError, children }) => {
  const navigate = useNavigate();
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  const user = getCurrentUser();
  const username = user?.username;

  const handleLogout = () => {
    clearAuth();
    navigate("/"); // HomePage route
  };

  const toggleDropdown = () => {
    setIsDropdownOpen((prev) => !prev);
  };

  const toggleSidebar = () => {
    setIsSidebarOpen((prev) => !prev);
  };

  const closeSidebar = () => {
    setIsSidebarOpen(false);
  };

  return (
    <div className={`users-layout ${isSidebarOpen ? "sidebar-open" : ""}`}>
      {/* Left sidebar */}
      <aside className="users-sidebar">
        <div className="sidebar-logo">
          <img src={ShardLogo} alt="Shard Logo" />
        </div>

        <nav className="sidebar-nav" onClick={closeSidebar}>
          <NavLink to="/user-dashboard" className={({ isActive }) => "sidebar-link" + (isActive ? " sidebar-link-active" : "") } >
            All Files
          </NavLink>  
          <NavLink to="/shared" className="sidebar-link">
            Shared
          </NavLink>
          <NavLink to="/activity-history" className={({ isActive }) => "sidebar-link" + (isActive ? " sidebar-link-active" : "") } >
            Activity History
          </NavLink>
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
              {storageUsage.used_gb} GB of {storageUsage.storage_limit_gb} GB used
            </span>
          )}
        </div>
      </aside>

      {/* Top header bar */}
      <header className="users-header">
        <div className="header-left">
          {/* Hamburger for mobile */}
          <button
            className="sidebar-toggle"
            type="button"
            onClick={toggleSidebar}
          >
            ☰
          </button>
        </div>

        <div className="header-right">
          <div className="user-dropdown-wrapper">
            <button
              className="user-dropdown-toggle"
              type="button"
              onClick={toggleDropdown}
            >
              Welcome, {username} ⏷
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

          <button className="logout-button" type="button" onClick={handleLogout}>
            Log out
          </button>
        </div>
      </header>

      {/* Main content area placeholder */}
      <main className="users-main-content">
        {children}
      </main>
    </div>
  );
};

export default UsersNavBar;
