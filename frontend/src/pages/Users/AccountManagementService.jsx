import React, { useEffect, useState } from "react";
import "../../styles/Users/AccountManagement.css";
import { upgradeAccount, downgradeAccount } from "../../services/AccountManagementService";
import { getStorageUsage } from "../../services/UserService";
import { useOutletContext } from "react-router-dom";

const MIN_MONTHLY_COST = 10;

const AccountManagement = () => {
  const { refreshUsage } = useOutletContext();
  const [loading, setLoading] = useState(true);
  const [usage, setUsage] = useState(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [upgradeCost, setUpgradeCost] = useState(MIN_MONTHLY_COST);
  const [upgrading, setUpgrading] = useState(false);
  const [downgrading, setDowngrading] = useState(false);

  const loadUsage = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await getStorageUsage();
      setUsage(data);
    } catch (err) {
      setError(err.message || "Failed to load storage usage");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadUsage();
  }, []);

  const handleUpgrade = async (e) => {
    e.preventDefault();
    setError("");
    setSuccess("");

    if (!upgradeCost || Number(upgradeCost) < MIN_MONTHLY_COST) {
      setError(`Minimum monthly cost is ${MIN_MONTHLY_COST}`);
      return;
    }

    try {
      setUpgrading(true);
      const data = await upgradeAccount(Number(upgradeCost));
      setSuccess(data.message || "Account upgraded successfully");
      await loadUsage();
      // Re-fetch storage usage so navbar updates
      if (typeof refreshUsage === "function") {
        await refreshUsage();
      }
    } catch (err) {
      setError(err.message || "Upgrade failed");
    } finally {
      setUpgrading(false);
    }
  };
          
  const handleDowngrade = async () => {
    if (!window.confirm("Are you sure you want to downgrade to FREE?")) {
      return;
    }

    setError("");
    setSuccess("");
    try {
      setDowngrading(true);
      const data = await downgradeAccount();
      setSuccess(data.message || "Account downgraded to FREE");
      await loadUsage();
      // Re-fetch storage usage so navbar updates
      if (typeof refreshUsage === "function") {
        await refreshUsage();
      }
    } catch (err) {
      setError(err.message || "Downgrade failed");
    } finally {
      setDowngrading(false);
    }
  };

  const renderUsageBar = () => {
    if (!usage) return null;
    const pct = Math.min(100, Math.max(0, usage.usage_percentage || 0));

    let barClass = "usage-bar-fill";
    if (pct >= 90) barClass += " danger";
    else if (pct >= 70) barClass += " warning";

    return (
      <div className="usage-bar">
        <div className={barClass} style={{ width: `${pct}%` }} />
      </div>
    );
  };

  const currentPlanStorage =
    usage && usage.storage_limit_gb ? usage.storage_limit_gb : 0;

  const projectedStorage =
    upgradeCost && !isNaN(upgradeCost)
      ? Math.floor(Number(upgradeCost) * 3)
      : 0;

  return (
    <div className="account-page">
      <h1 className="account-title">Account & Storage</h1>

      {error && <div className="account-alert error">{error}</div>}
      {success && <div className="account-alert success">{success}</div>}

      {loading && !usage ? (
        <div className="account-loading">Loading account details...</div>
      ) : (
        <div className="account-grid">
          {/* Storage overview card */}
          <div className="account-card">
            <h2 className="card-title">Storage overview</h2>
            {usage && (
              <>
                <div className="badge-row">
                  <span className={`plan-badge ${usage.account_type.toLowerCase()}`}>
                    {usage.account_type}
                  </span>
                  {usage.monthly_cost != null && (
                    <span className="cost-badge">
                      ${usage.monthly_cost.toFixed(2)}/month
                    </span>
                  )}
                </div>

                <div className="usage-stats">
                  <div className="usage-stat">
                    <span className="usage-label">Used</span>
                    <span className="usage-value">
                      {usage.used_gb} GB / {usage.storage_limit_gb} GB
                    </span>
                  </div>
                  <div className="usage-stat">
                    <span className="usage-label">Remaining</span>
                    <span className="usage-value">
                      {usage.remaining_gb} GB
                    </span>
                  </div>
                  <div className="usage-stat">
                    <span className="usage-label">Usage</span>
                    <span className="usage-value">
                      {usage.usage_percentage}%
                    </span>
                  </div>
                  {usage.renewal_date && (
                    <div className="usage-stat">
                      <span className="usage-label">Next renewal</span>
                      <span className="usage-value">
                        {new Date(usage.renewal_date).toLocaleDateString()}
                      </span>
                    </div>
                  )}
                </div>

                {renderUsageBar()}

                <p className="usage-hint">
                  Keep some free space to avoid upload interruptions.
                </p>
              </>
            )}
          </div>

          {/* Plan actions card */}
          <div className="account-card">
            <h2 className="card-title">Plan settings</h2>

            <form className="upgrade-form" onSubmit={handleUpgrade}>
              <label className="field-label" htmlFor="monthlyCost">
                Monthly budget (USD)
              </label>
              <input
                id="monthlyCost"
                type="number"
                min={MIN_MONTHLY_COST}
                step="1"
                className="field-input"
                value={upgradeCost}
                onChange={(e) => setUpgradeCost(e.target.value)}
              />

              <div className="upgrade-summary">
                <div>
                  <span className="upgrade-label">Current storage</span>
                  <span className="upgrade-value">
                    {currentPlanStorage} GB
                  </span>
                </div>
                <div>
                  <span className="upgrade-label">Projected storage</span>
                  <span className="upgrade-value">
                    {projectedStorage} GB
                  </span>
                </div>
              </div>

              <button
                type="submit"
                className="btn primary"
                disabled={upgrading}
              >
                {upgrading ? "Updating plan..." : "Upgrade / Update plan"}
              </button>
            </form>

            {usage && usage.account_type === "PAID" && (
              <div className="divider" />

            )}

            {usage && usage.account_type === "PAID" && (
              <div className="downgrade-section">
                <h3 className="downgrade-title">Downgrade to FREE</h3>
                <p className="downgrade-text">
                  Downgrading will reduce your storage limit to 2 GB. Make sure
                  your current usage fits within the free limit before
                  proceeding.
                </p>
                <button
                  type="button"
                  className="btn danger"
                  onClick={handleDowngrade}
                  disabled={downgrading}
                >
                  {downgrading ? "Processing..." : "Downgrade to FREE"}
                </button>
              </div>
            )}

            {usage && usage.account_type === "FREE" && (
              <p className="upgrade-note">
                You are currently on a FREE plan with {usage.storage_limit_gb} GB
                of storage. Increase your monthly budget to unlock more space.
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default AccountManagement;