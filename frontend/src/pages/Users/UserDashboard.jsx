import React, { useRef, useState, useEffect } from "react";
import "../../styles/Users/UserDashboard.css";
import { createFolder, uploadFile, listFiles, downloadFile, getFileInfo, searchFiles } from "../../services/UserService";

const UserDashboard = () => {
  const [currentPath, setCurrentPath] = useState("/");
  const [currentFolderId, setCurrentFolderId] = useState(null); // null = root
  const [isCreatingFolder, setIsCreatingFolder] = useState(false);
  const [newFolderName, setNewFolderName] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [erasureLevel, setErasureLevel] = useState("MEDIUM");
  const [files, setFiles] = useState([]);

  const [openMenuFileId, setOpenMenuFileId] = useState(null);

  const toggleMenu = (fileId) => {
    setOpenMenuFileId((prev) => (prev === fileId ? null : fileId));
  };

  const closeMenu = () => setOpenMenuFileId(null);

  // Load files when dashboard mounts
  useEffect(() => {
    const load = async () => {
      try {
        const data = await listFiles();
        setFiles(data);
      } catch (err) {
        console.error(err);
      }
    };
    load();
  }, []);

  function formatFileSize(bytes) {
  if (!bytes && bytes !== 0) return "";
  if (bytes === 0) return "0 B";

  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = bytes;
  let unitIndex = 0;

  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }

  const decimals = size < 10 && unitIndex > 0 ? 2 : size < 100 ? 1 : 0;
  return `${size.toFixed(decimals)} ${units[unitIndex]}`;
}

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
    const selectedFiles = Array.from(e.target.files || []);
    if (selectedFiles.length === 0) return;

    setIsLoading(true);
    try {
      // Upload sequentially; you can parallelize later if needed
      for (const file of selectedFiles) {
        // eslint-disable-next-line no-await-in-loop
        await uploadFile({
          file,
          folderId: currentFolderId,
          erasureId: erasureLevel,
        });
      }

      // After all uploads, refresh list once
      const data = await listFiles();
      setFiles(data);
    } catch (err) {
      console.error(err);
      alert(err.message || "Failed to upload one or more files");
    } finally {
      setIsLoading(false);
      e.target.value = ""; // allow selecting same files again
    }
  };

  const handleDownload = async (file) => {
    try {
      await downloadFile(file.file_id, file.file_name);
    } catch (err) {
      console.error(err);
      alert(err.message || "Failed to download file");
    }
  };

  // File Info modal state
  const [fileInfoModalOpen, setFileInfoModalOpen] = useState(false);
  const [fileInfoData, setFileInfoData] = useState(null);

  const openFileInfo = async (file) => {
    try {
      const info = await getFileInfo(file.file_id);
      setFileInfoData(info);
      setFileInfoModalOpen(true);
    } catch (err) {
      console.error(err);
      alert(err.message || "Failed to load file info");
    }
  };

  const closeFileInfo = () => {
    setFileInfoModalOpen(false);
    setFileInfoData(null);
  };

// Search state
const [searchQuery, setSearchQuery] = useState("");
const handleSearchChange = (e) => {
  setSearchQuery(e.target.value);
};

const handleSearchSubmit = async (e) => {
  e.preventDefault();
  try {
    const data = await searchFiles(searchQuery.trim());
    setFiles(data);
  } catch (err) {
    console.error(err);
    alert(err.message || "Failed to search files");
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
          <form onSubmit={handleSearchSubmit}>
            <input
              className="search-input"
              type="text"
              placeholder="Search files by name"
              value={searchQuery}
              onChange={handleSearchChange}
            />
          </form>
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
            multiple 
          />
          {/* Erasure level selector */}
          <select
            className="toolbar-select"
            value={erasureLevel}
            onChange={(e) => setErasureLevel(e.target.value)}
            disabled={isLoading}
          >
            <option value="LOW">Low</option>
            <option value="MEDIUM">Medium</option>
            <option value="HIGH">High</option>
          </select>
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
            {files.length === 0 ? (
              <tr>
                <td colSpan={4} style={{ textAlign: "center" }}>
                  No files found
                </td>
              </tr>
            ) : (
              files.map((file) => (
                <tr key={file.file_id}>
                  <td>{file.file_name}</td>
                  <td>{formatFileSize(file.file_size)}</td>
                  <td>{new Date(file.uploaded_at).toLocaleString()}</td>
                  <td className="table-actions-cell">
                    <div className="actions-menu-wrapper">
                      <button
                        type="button"
                        className="table-action-trigger"
                        onClick={() => toggleMenu(file.file_id)}
                      >
                        ⋮
                      </button>

                      {openMenuFileId === file.file_id && (
                        <div className="actions-menu-dropdown">
                          <button
                            type="button"
                            className="actions-menu-item"
                            onClick={() => {
                              closeMenu();
                              handleDownload(file);
                            }}
                          >
                            Download
                          </button>
                          <button
                            type="button"
                            className="actions-menu-item"
                            onClick={() => {
                              closeMenu();
                              // TODO: implement delete
                              alert("Delete not implemented yet");
                            }}
                          >
                            Delete
                          </button>
                          <button
                            type="button"
                            className="actions-menu-item"
                            onClick={() => {
                              closeMenu();
                              // TODO: implement share
                              alert("Move not implemented yet");
                            }}
                          >
                            Move
                          </button>
                          <button
                            type="button"
                            className="actions-menu-item"
                            onClick={() => {
                              closeMenu();
                              // TODO: implement share
                              alert("Share not implemented yet");
                            }}
                          >
                            Share
                          </button>
                          <button
                            type="button"
                            className="actions-menu-item"
                            onClick={() => {
                              closeMenu();
                              openFileInfo(file);
                            }}
                          >
                            File Info
                          </button>
                        </div>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
  {fileInfoModalOpen && fileInfoData && (
    <div className="modal-backdrop" onClick={closeFileInfo}>
      <div
        className="modal-content"
        onClick={(e) => e.stopPropagation()} // prevent close when clicking inside
      >
        <h3 className="modal-title">File Info</h3>
        <div className="modal-body">
          <p><strong>Name:</strong> {fileInfoData.file_name}</p>
          <p><strong>Size:</strong> {formatFileSize(fileInfoData.file_size)}</p>
          <p><strong>Uploaded:</strong> {new Date(fileInfoData.uploaded_at).toLocaleString()}</p>
          <p><strong>Erasure Profile:</strong> {fileInfoData.erasure_id}</p>
          <p><strong>Logical Path:</strong> {fileInfoData.logical_path}</p>
        </div>
        <div className="modal-footer">
          <button type="button" className="toolbar-action-btn" onClick={closeFileInfo}>
            Close
          </button>
        </div>
      </div>
    </div>
  )}
    </div>
  );
};

export default UserDashboard;
