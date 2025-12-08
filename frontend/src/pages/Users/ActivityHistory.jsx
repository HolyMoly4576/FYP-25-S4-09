import React, { useEffect, useState } from "react";
import "../../styles/Users/ActivityHistory.css";
import { getActivityHistory } from "../../services/ActivityHistoryService";

const PAGE_LIMIT = 20;

function ActivityHistory() {
  const [activities, setActivities] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [dateFilter, setDateFilter] = useState("");
  const [actionFilter, setActionFilter] = useState("");
  const [dateFilterApplied, setDateFilterApplied] = useState("");
  const [actionFilterApplied, setActionFilterApplied] = useState("");

  const loadActivities = async (customOffset) => {
    setLoading(true);
    setError("");

    try {
      const result = await getActivityHistory({
        dateFilter: dateFilterApplied || undefined,
        actionType: actionFilterApplied || undefined,
        limit: PAGE_LIMIT,
        offset: customOffset ?? offset,
      });

      setActivities(result.activities);
      setTotal(result.total);
      setOffset(result.offset);
    } catch (err) {
      setError(err.message || "Failed to load activity history.");
      setActivities([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadActivities(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dateFilterApplied, actionFilterApplied]);

  const handleApplyFilters = () => {
    setOffset(0);
    setDateFilterApplied(dateFilter.trim());
    setActionFilterApplied(actionFilter.trim().toUpperCase());
  };

  const handleClearFilters = () => {
    setDateFilter("");
    setActionFilter("");
    setDateFilterApplied("");
    setActionFilterApplied("");
    setOffset(0);
    // also refresh list with cleared filters
    loadActivities(0);
  };

  const formatDateTime = (isoString) => {
    if (!isoString) return "-";
    try {
      const d = new Date(isoString);
      if (Number.isNaN(d.getTime())) return isoString;
      return d.toLocaleString();
    } catch {
      return isoString;
    }
  };

  const renderDetails = (details) => {
    if (!details || typeof details !== "object") return "-";
    try {
      return JSON.stringify(details, null, 2);
    } catch {
      return "-";
    }
  };

  const getActionBadgeClass = (actionType) => {
    if (!actionType) return "badge badge-default";
    const lower = actionType.toLowerCase();
    if (lower === "login") return "badge badge-login";
    if (lower === "logout") return "badge badge-logout";
    if (lower === "file_upload" || lower === "upload") {
      return "badge badge-file_upload";
    }
    return "badge badge-default";
  };

  return (
    <div className="activity-history">
      <div className="activity-history-header">
        <h2 className="activity-history-title">Activity History</h2>
        <p className="activity-history-subtitle">
          View your recent actions, filter by date or action type, and inspect details.
        </p>
      </div>

      <div className="activity-history-filters">
        <div className="filter-group">
          <label htmlFor="dateFilter">Date</label>
          <input
            id="dateFilter"
            type="date"
            value={dateFilter}
            onChange={(e) => setDateFilter(e.target.value)}
          />
        </div>

        <div className="filter-group">
          <label htmlFor="actionFilter">Action type</label>
          <input
            id="actionFilter"
            type="text"
            placeholder="e.g. LOGIN, FILE_UPLOAD"
            value={actionFilter}
            onChange={(e) => setActionFilter(e.target.value)}
          />
        </div>

        <div className="filter-buttons">
          <button
            className="btn btn-primary"
            onClick={handleApplyFilters}
            disabled={loading}
          >
            Apply
          </button>
          <button
            className="btn btn-secondary"
            onClick={handleClearFilters}
            disabled={loading || (!dateFilter && !actionFilter)}
          >
            Clear
          </button>
        </div>
      </div>

      {loading && (
        <div className="activity-history-status">
          Loading activity history...
        </div>
      )}

      {error && !loading && (
        <div className="activity-history-error">
          {error}
        </div>
      )}

      {!loading && !error && activities.length === 0 && (
        <div className="activity-history-empty">
          No activity records found for the selected filters.
        </div>
      )}

      {!loading && !error && activities.length > 0 && (
        <>
          <div className="activity-history-meta">
            <span>
              Showing {activities.length} of {total} activities
            </span>
            {dateFilterApplied && (
              <span className="chip">
                Date: {dateFilterApplied}
              </span>
            )}
            {actionFilterApplied && (
              <span className="chip">
                Action: {actionFilterApplied}
              </span>
            )}
          </div>

          <div className="activity-history-table-wrapper">
            <table className="activity-history-table">
              <thead>
                <tr>
                  <th>Date / Time</th>
                  <th>Action</th>
                  <th>Resource</th>
                  <th>IP</th>
                  <th>User Agent</th>
                  <th>Details</th>
                </tr>
              </thead>
              <tbody>
                {activities.map((activity) => (
                  <tr key={activity.activity_id}>
                    <td>{formatDateTime(activity.created_at)}</td>
                    <td className="col-action">
                      <span className={getActionBadgeClass(activity.action_type)}>
                        {activity.action_type}
                      </span>
                    </td>
                    <td>
                      {activity.resource_type || "-"}
                      {activity.resource_id ? ` (#${activity.resource_id})` : ""}
                    </td>
                    <td>{activity.ip_address || "-"}</td>
                    <td className="col-user-agent">
                      {activity.user_agent || "-"}
                    </td>
                    <td>
                      <pre className="details-pre">
                        {renderDetails(activity.details)}
                      </pre>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

export default ActivityHistory;