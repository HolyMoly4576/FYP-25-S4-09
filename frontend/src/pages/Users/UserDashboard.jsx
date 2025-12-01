import React from "react";
import "../../styles/Users/UserDashboard.css";

const UserDashboard = () => {
  return (
    <div className="dashboard-container">
      {/* Top controls: current folder + search + actions */}
      <div className="dashboard-toolbar">
        <div className="toolbar-left">
          <label className="toolbar-label">Current Folder Location</label>
          <input
            className="toolbar-input"
            type="text"
            value="/"
            readOnly
          />
        </div>

        <div className="toolbar-center">
          <input
            className="search-input"
            type="text"
            placeholder="Search"
          />
        </div>

        <div className="toolbar-right">
          <button className="toolbar-action-btn">+ Create Folder</button>
          <button className="toolbar-action-btn">+ Upload File</button>
        </div>
      </div>

      {/* Files table */}
      <div className="dashboard-table-wrapper">
        <table className="dashboard-table">
          <thead>
            <tr>
              <th>File / Folder Name</th>
              <th>Size</th>
              <th>Modified Date</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {/* Placeholder row */}
            <tr>
              <td>Example_File.txt</td>
              <td>100 KB</td>
              <td>29/10/2025 09:05:05</td>
              <td className="table-actions-cell">
                <button className="table-action-trigger">⋮</button>
                {/* Later: dropdown with Share / Details / Move/Copy / Download / Delete */}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* Upload queue bar placeholder */}
      <div className="upload-queue-bar">
        <div className="upload-queue-title">Upload Queue</div>
        <div className="upload-queue-columns">
          <span>File</span>
          <span>Time Left</span>
          <span>Progress</span>
          <span>Status</span>
        </div>
        {/* Later: map over uploads and show rows */}
      </div>
    </div>
  );
};

export default UserDashboard;
