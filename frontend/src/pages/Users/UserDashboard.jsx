import React, { useRef, useState } from "react";
import "../../styles/Users/UserDashboard.css";
import { createFolder, uploadFile } from "../../services/UserService"; // adjust path if needed

const UserDashboard = () => {
  const [currentPath, setCurrentPath] = useState("/");
  const [currentFolderId, setCurrentFolderId] = useState(null); // null = root
  const [isCreatingFolder, setIsCreatingFolder] = useState(false);
  const [newFolderName, setNewFolderName] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleCreateFolderClick = () => {
    setIsCreatingFolder(true);
  };

  const handleCreateFolderCancel = () => {
    setIsCreatingFolder(false);
    setNewFolderName("");
  };

  const handleCreateFolderConfirm = async () => {
    const trimmed = newFolderName.trim();
    if (!trimmed) {
      alert("Folder name cannot be empty");
      return;
    }

    setIsLoading(true);
    try {
      const folder = await createFolder({
        name: trimmed,
        parentFolderId: currentFolderId,
      });

      console.log("Created folder:", folder);
      // TODO: refresh folder list here when you implement listing

      setIsCreatingFolder(false);
      setNewFolderName("");
    } catch (err) {
      console.error(err);
      alert(err.message || "Failed to create folder");
    } finally {
      setIsLoading(false);
    }
  };

  const fileInputRef = useRef(null); 

  const handleUploadClick = () => {
    if (fileInputRef.current) {
      fileInputRef.current.click();
    }
  };

  const handleFileChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsLoading(true);
    try {
      const res = await uploadFile({
        file,
        folderId: currentFolderId,
        erasureId: "MEDIUM", // or allow user to pick
      });
      console.log("Uploaded file:", res);
      // TODO: refresh file list
    } catch (err) {
      console.error(err);
      alert(err.message || "Failed to upload file");
    } finally {
      setIsLoading(false);
      e.target.value = ""; // reset input so same file can be re-selected
    }
  };
  return (
    <div className="dashboard-container">
      {/* Top controls: current folder + search + actions */}
      <div className="dashboard-toolbar">
        <div className="toolbar-left">
          <label className="toolbar-label">Current Folder Location</label>
          <input
            className="toolbar-input"
            type="text"
            value={currentPath}
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
          <button
            className="toolbar-action-btn"
            onClick={handleCreateFolderClick}
            disabled={isLoading}
          >
            + Create Folder
          </button>
          <input
            type="file"
            ref={fileInputRef}
            style={{ display: "none" }}
            onChange={handleFileChange}
          />
          <button
            className="toolbar-action-btn"
            onClick={handleUploadClick}
            disabled={isLoading}
          >
            + Upload File
          </button>
        </div>
      </div>

      {/* Inline create-folder bar */}
      {isCreatingFolder && (
        <div className="create-folder-bar">
          <input
            type="text"
            className="toolbar-input"
            placeholder="Folder name"
            value={newFolderName}
            onChange={(e) => setNewFolderName(e.target.value)}
            disabled={isLoading}
          />
          <button
            className="toolbar-action-btn"
            onClick={handleCreateFolderConfirm}
            disabled={isLoading}
          >
            Create
          </button>
          <button
            className="toolbar-action-btn"
            onClick={handleCreateFolderCancel}
            disabled={isLoading}
          >
            Cancel
          </button>
        </div>
      )}

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
            <tr>
              <td>Example_File.txt</td>
              <td>100 KB</td>
              <td>29/10/2025 09:05:05</td>
              <td className="table-actions-cell">
                <button className="table-action-trigger">⋮</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default UserDashboard;
