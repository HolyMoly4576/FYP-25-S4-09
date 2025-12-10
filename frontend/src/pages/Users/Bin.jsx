import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import "../../styles/Users/Bin.css";
import {
  listBinItems,
  getBinStats,
  restoreBinItem,
  emptyBin,
  permanentDeleteBinItem,
} from "../../services/BinService";

function formatFileSize(bytes) {
  if (bytes === 0 || bytes === null || bytes === undefined) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
}

const Bin = () => {
  const navigate = useNavigate();

  const [items, setItems] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState(null); // { type: "success" | "error", text: string }
  const [emptying, setEmptying] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const showMessage = (text, type) => {
    setMessage({ text, type });
    setTimeout(() => {
      setMessage(null);
    }, 5000);
  };

  const loadStats = async () => {
    try {
      const s = await getBinStats();
      setStats(s);
    } catch (err) {
      console.error(err);
    }
  };

  const loadItems = async () => {
    try {
      setRefreshing(true);
      const list = await listBinItems();
      setItems(list);
      await loadStats();
    } catch (err) {
      console.error(err);
      showMessage(err.message || "Failed to load recycle bin", "error");
    } finally {
      setRefreshing(false);
      setLoading(false);
    }
  };

  useEffect(() => {
    loadItems();
    const interval = setInterval(() => {
      loadStats();
    }, 30000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleRestore = async (item) => {
    const ok = window.confirm(`Restore "${item.original_name}"?`);
    if (!ok) return;
    try {
      const res = await restoreBinItem(item.bin_id);
      showMessage(res.message || "Item restored", "success");
      await loadItems();
    } catch (err) {
      console.error(err);
      showMessage(err.message || "Failed to restore item", "error");
    }
  };

  const handlePermanentDelete = async (item) => {
    const ok = window.confirm(
      `PERMANENTLY delete "${item.original_name}"?\n\nThis action cannot be undone!`
    );
    if (!ok) return;
    try {
      const res = await permanentDeleteBinItem(item.bin_id);
      showMessage(res.message || "Item permanently deleted", "success");
      await loadItems();
    } catch (err) {
      console.error(err);
      showMessage(err.message || "Failed to permanently delete item", "error");
    }
  };

  const handleEmptyBin = async () => {
    const ok = window.confirm(
      "PERMANENTLY DELETE ALL items in the recycle bin?\n\nThis action cannot be undone!"
    );
    if (!ok) return;
    try {
      setEmptying(true);
      const res = await emptyBin();
      showMessage(res.message || "Recycle bin emptied", "success");
      await loadItems();
    } catch (err) {
      console.error(err);
      showMessage(err.message || "Failed to empty recycle bin", "error");
    } finally {
      setEmptying(false);
    }
  };

  const renderItems = () => {
    if (loading) {
      return (
        <div className="bin-loading">
          Loading recycle bin...
        </div>
      );
    }

    if (!items || items.length === 0) {
      return (
        <div className="bin-empty-state">
          <h3>🗑️ Recycle Bin is Empty</h3>
          <p>
            Deleted files and folders will appear here and be automatically removed
            after 30 days.
          </p>
        </div>
      );
    }

    return (
      <div className="bin-items">
        {items.map((item) => {
          const isExpiring = item.days_remaining <= 7;
          const statusClass = isExpiring
            ? "bin-status-expiring"
            : "bin-status-normal";
          const statusText = isExpiring
            ? `${item.days_remaining} days left`
            : `${item.days_remaining} days remaining`;
          const icon = item.resource_type === "FILE" ? "📄" : "📁";
          const sizeText = item.original_size
            ? formatFileSize(item.original_size)
            : null;

          return (
            <div key={item.bin_id} className="bin-item-row">
              <div className="bin-item-info">
                <div className="bin-item-name">
                  <span>{icon}</span>
                  <span>{item.original_name}</span>
                </div>
                <div className="bin-item-meta">
                  <span>Type: {item.resource_type}</span>
                  {sizeText && <span>Size: {sizeText}</span>}
                  <span>
                    Deleted: {new Date(item.deleted_at).toLocaleDateString()}
                  </span>
                  <span>Path: {item.original_path || "Unknown"}</span>
                  <span className={`bin-status ${statusClass}`}>
                    {statusText}
                  </span>
                </div>
              </div>
              <div className="bin-item-actions">
                <button
                  type="button"
                  className="bin-btn bin-btn-success"
                  onClick={() => handleRestore(item)}
                >
                  ↩️ Restore
                </button>
                <button
                  type="button"
                  className="bin-btn bin-btn-danger"
                  onClick={() => handlePermanentDelete(item)}
                >
                  🗑️ Delete Forever
                </button>
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <div className="bin-page-root">
      <div className="bin-container">
        <div className="bin-header">
          <h1 className="bin-header-title">🗑️ Recycle Bin</h1>
          <p className="bin-header-subtitle">
            Deleted files and folders (30-day retention)
          </p>
        </div>

        <div className="bin-content">
          {message && (
            <div
              className={[
                "bin-message",
                message.type === "error"
                  ? "bin-message-error"
                  : "bin-message-success",
              ].join(" ")}
            >
              {message.text}
            </div>
          )}

          {stats && (
            <div className="bin-stats-section">
              <div className="bin-stat-card">
                <div className="bin-stat-number">
                  {stats.total_items}
                </div>
                <div className="bin-stat-label">Total Items</div>
              </div>
              <div className="bin-stat-card">
                <div className="bin-stat-number">
                  {formatFileSize(stats.total_size_bytes)}
                </div>
                <div className="bin-stat-label">Total Size</div>
              </div>
              <div className="bin-stat-card">
                <div className="bin-stat-number">
                  {stats.items_expiring_soon}
                </div>
                <div className="bin-stat-label">Expiring Soon</div>
              </div>
              <div className="bin-stat-card">
                <div className="bin-stat-number">
                  {stats.files_count}
                </div>
                <div className="bin-stat-label">Files</div>
              </div>
            </div>
          )}

          <div className="bin-actions-bar">
            <button
              type="button"
              className="bin-btn bin-btn-secondary"
              onClick={loadItems}
              disabled={refreshing}
            >
              🔄 {refreshing ? "Refreshing..." : "Refresh"}
            </button>
            <button
              type="button"
              className="bin-btn bin-btn-danger"
              onClick={handleEmptyBin}
              disabled={emptying || (stats && stats.total_items === 0)}
            >
              🗑️ {emptying ? "Emptying..." : "Empty Bin"}
            </button>
            <button
              type="button"
              className="bin-btn bin-btn-secondary bin-back-link"
              onClick={() => navigate("/user-dashboard")}
            >
              📁 Back to Files
            </button>
          </div>

          <div className="bin-list-container">
            {renderItems()}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Bin;