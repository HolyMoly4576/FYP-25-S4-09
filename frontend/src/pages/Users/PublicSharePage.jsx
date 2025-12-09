// frontend/src/pages/PublicSharePage.jsx
import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { API_BASE_URL } from "../../services/UserService";
import "../../styles/Users/PublicSharePage.css"; 

const PublicSharePage = () => {
  const { token } = useParams();
  const [loading, setLoading] = useState(true);
  const [info, setInfo] = useState(null);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [accessResult, setAccessResult] = useState(null);
  const [accessLoading, setAccessLoading] = useState(false);

  // Load share info
  useEffect(() => {
    const loadInfo = async () => {
      setLoading(true);
      setError("");
      try {
        const res = await fetch(`${API_BASE_URL}/shares/files/info/${token}`);
        const data = await res.json();
        if (!res.ok) {
          throw new Error(data.detail || data.message || "Failed to load share info");
        }
        setInfo(data);
      } catch (err) {
        setError(err.message || "Failed to load share info");
      } finally {
        setLoading(false);
      }
    };

    if (token) {
      loadInfo();
    }
  }, [token]);

  const handleAccess = async () => {
    setError("");
    setAccessLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/shares/files/access`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          share_token: token,
          password: password.trim() || null,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || data.message || "Access denied");
      }

      setAccessResult(data);

      // If DOWNLOAD, redirect to backend download_url
      if (data.permissions === "DOWNLOAD" && data.download_url) {
        window.location.href = data.download_url;
      }
    } catch (err) {
      setError(err.message || "Failed to access shared file");
    } finally {
      setAccessLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="public-share-container">
        <div className="public-share-card">Loading shared file...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="public-share-container">
        <div className="public-share-card public-share-error">{error}</div>
      </div>
    );
  }

  if (!info) {
    return (
      <div className="public-share-container">
        <div className="public-share-card">Share not found.</div>
      </div>
    );
  }

  const isExpired = info.is_expired;

  return (
    <div className="public-share-container">
      <div className="public-share-card">
        <h2>Shared File</h2>
        <p>
          <strong>Name:</strong> {info.resource_name}
        </p>
        <p>
          <strong>Shared by:</strong> {info.shared_by_username}
        </p>
        <p>
          <strong>Permissions:</strong> {info.permissions}
        </p>
        {info.expires_at && (
          <p>
            <strong>Expires:</strong>{" "}
            {new Date(info.expires_at).toLocaleString()}
          </p>
        )}
        {isExpired && (
          <p style={{ color: "#c53030", marginTop: 8 }}>
            This share link has expired.
          </p>
        )}

        {!isExpired && (
          <>
            {info.requires_password && (
              <div className="form-group" style={{ marginTop: 16 }}>
                <label>One-Time Password (Required)</label>
                <input
                  type="password"
                  className="toolbar-input"
                  placeholder="Enter the one-time password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
            )}

            {!info.requires_password && (
              <p style={{ marginTop: 16, color: "#64748b" }}>
                No password required for this share.
              </p>
            )}

            <button
              type="button"
              className="toolbar-action-btn"
              style={{ marginTop: 16 }}
              onClick={handleAccess}
              disabled={accessLoading}
            >
              {accessLoading ? "Checking..." : "Download"}
            </button>

            {accessResult && info.permissions !== "DOWNLOAD" && (
              <div style={{ marginTop: 16, fontSize: 14 }}>
                <p>
                  <strong>File size:</strong>{" "}
                  {accessResult.file_size ?? "Unknown"}
                </p>
                {accessResult.uploaded_at && (
                  <p>
                    <strong>Uploaded at:</strong>{" "}
                    {new Date(accessResult.uploaded_at).toLocaleString()}
                  </p>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default PublicSharePage;