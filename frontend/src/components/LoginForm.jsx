import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { getRoles, loginUser } from "../services/authService";
import "../styles/LoginForm.css";

function isEmail(str) {
  // Simple email regex
  return /^[\w-.]+@([\w-]+\.)+[\w-]{2,4}$/.test(str);
}

function LoginForm({ toggle }) {
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [roles, setRoles] = useState([]);
  const [selectedRole, setSelectedRole] = useState("");
  const [formMessage, setFormMessage] = useState(""); // only for form validation/login
  const [rolesError, setRolesError] = useState("");   // only for roles fetch
  const [showSuccessAlert, setShowSuccessAlert] = useState(false);
  const [loading, setLoading] = useState(false);

  const navigate = useNavigate();

  useEffect(() => {
    async function fetchRoles() {
      try {
        const data = await getRoles();
        if (Array.isArray(data) && data.length > 0) {
          setRoles(data);
          setSelectedRole(data[0]);
          setRolesError(""); // clear existing fetch error if successful
        } else {
          setRoles(["FREE", "PAID", "SYSADMIN"]);
          setSelectedRole("FREE");
          setRolesError("No roles found. Using default options.");
        }
      } catch (err) {
        setRoles(["FREE", "PAID", "SYSADMIN"]);
        setSelectedRole("FREE");
        setRolesError("Could not fetch roles. Using defaults.");
      }
    }
    fetchRoles();
  }, []);

  // Helper: Validate identifier before submission
  const validate = () => {
    if (!identifier) {
      setFormMessage("Please enter your username or email.");
      return false;
    }
    if (identifier.includes("@") && !isEmail(identifier)) {
      setFormMessage("Please enter a valid email address.");
      return false;
    }
    if (!password) {
      setFormMessage("Please enter your password.");
      return false;
    }
    if (!selectedRole) {
      setFormMessage("Please select your role.");
      return false;
    }
    setFormMessage("");
    return true;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setFormMessage("");
    if (!validate()) return;

    setLoading(true);
    try {
      await loginUser({
        username_or_email: identifier,
        password,
        account_type: selectedRole, // as required by your backend
      });
      localStorage.setItem("username", identifier);
      localStorage.setItem("role", selectedRole);
      setShowSuccessAlert(true);
      setTimeout(() => {
        setShowSuccessAlert(false);
        if (selectedRole === "SYSADMIN") {
          navigate("/Admin/Admin-Dashboard");
        } else {
          navigate("/User/User-Dashboard");
        }
        toggle && toggle();
      }, 1200);
    } catch (err) {
      setFormMessage(err.message || "Login failed. Please try again.");
      setTimeout(() => setFormMessage(""), 3500);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="popup">
      <div className="popup-inner">
        <h2>Login</h2>
        <form onSubmit={handleSubmit} className="login-form">
          <label>
            Username or Email:
            <input
              type="text"
              value={identifier}
              onChange={e => setIdentifier(e.target.value)}
              placeholder="Enter username or email"
              required
              autoComplete="username"
            />
          </label>
          <label>
            Password:
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
              autoComplete="current-password"
            />
          </label>
          <label>
            Select Role:
            <select
              value={selectedRole}
              onChange={e => setSelectedRole(e.target.value)}
              required
            >
              {roles.map((role, idx) => (
                <option key={idx} value={role}>
                  {role.charAt(0).toUpperCase() + role.slice(1).toLowerCase()}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" disabled={loading}>
            {loading ? "Logging in..." : "Login"}
          </button>
          {/* Only show fetch roles error if dropdown is empty */}
          {rolesError && roles.length === 0 && <p className="response">{rolesError}</p>}
          {formMessage && <p className="response">{formMessage}</p>}
        </form>
        <button type="button" className="close-btn" onClick={toggle}>
          Close
        </button>
        {showSuccessAlert && (
          <div className="custom-alert">
            <div className="custom-alert-content">
              <h3>Login Successful</h3>
              <p>Welcome <strong>{identifier}</strong>!</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default LoginForm;
