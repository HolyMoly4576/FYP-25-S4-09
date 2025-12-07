import React, { useRef, useState, useEffect } from "react";
import "../../styles/Users/UserDashboard.css";
import { createFolder, listFolders, moveFolder, uploadFile, listFiles, downloadFile, getFileInfo, searchFilesAndFolders, moveFile } from "../../services/UserService";

const UserDashboard = () => {
  const [currentPath, setCurrentPath] = useState("/");
  const [currentFolderId, setCurrentFolderId] = useState(null); // null = root
  const [isCreatingFolder, setIsCreatingFolder] = useState(false);
  const [newFolderName, setNewFolderName] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [erasureLevel, setErasureLevel] = useState("MEDIUM");
  const [files, setFiles] = useState([]);
  const [folders, setFolders] = useState([]);       
  const [searchQuery, setSearchQuery] = useState(""); 
  const [moveTargets, setMoveTargets] = useState({}); // { [fileId]: folderId | "" }
  const [dragItem, setDragItem] = useState(null); // { type: 'file' | 'folder', id: string }

  const [openMenuFileId, setOpenMenuFileId] = useState(null);

  const toggleMenu = (fileId) => {
    setOpenMenuFileId((prev) => (prev === fileId ? null : fileId));
  };

  const closeMenu = () => setOpenMenuFileId(null);

  // Load root folders and files on mount
  useEffect(() => {
    const loadInitial = async () => {
      try {
        const [foldersData, filesData] = await Promise.all([
          listFolders(null), // root folders
          listFiles(),
        ]);
        setFolders(foldersData);
        setFiles(filesData);
      } catch (err) {
        console.error(err);
      }
    };
    loadInitial();
  }, []);

  // Helper: reload folders for current folder
  const refreshFolders = async (folderId) => {
    try {
      const data = await listFolders(folderId || null);
      setFolders(data);
    } catch (err) {
      console.error(err);
    }
  };

  const handleCreateFolderConfirm = async () => {
    const trimmed = newFolderName.trim();
    if (!trimmed) {
      alert("Folder name cannot be empty");
      return;
    }

    setIsLoading(true);
    try {
      await createFolder({
        name: trimmed,
        parentFolderId: currentFolderId,
      });

      // reload folders for current folder
      await refreshFolders(currentFolderId);

      setIsCreatingFolder(false);
      setNewFolderName("");
    } catch (err) {
      console.error(err);
      alert(err.message || "Failed to create folder");
    } finally {
      setIsLoading(false);
    }
  };

  // Navigation
  const enterFolder = async (folder) => {
    const newFolderId = folder.folder_id;
    setCurrentFolderId(newFolderId);
    setCurrentPath((prev) =>
      prev === "/" ? `/${folder.name}` : `${prev}/${folder.name}`
    );
    await refreshFolders(newFolderId);
    // later: also filter/load files by folder if backend supports it
  };

  const goUpOneLevel = async () => {
    if (currentFolderId === null) return;

    const currentFolder = folders.find((f) => f.folder_id === currentFolderId);
    const parentId = currentFolder?.parent_folder_id || null;

    setCurrentFolderId(parentId);

    const parts = currentPath.split("/").filter(Boolean);
    parts.pop();
    setCurrentPath(parts.length ? `/${parts.join("/")}` : "/");

    await refreshFolders(parentId);
  };

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
  async function handleSearchSubmit(e) {
    e.preventDefault();
    try {
      const result = await searchFilesAndFolders(searchQuery);
      setFiles(result.files || []);
      setFolders(result.folders || []);
    } catch (err) {
      console.error(err);
      alert(err.message);
    }
  }

  function handleSearchChange(e) {
    setSearchQuery(e.target.value);
  }

  function handleCreateFolderCancel() {
    setIsCreatingFolder(false);
    setNewFolderName("");
  }

  // Derive visible files – currently not folder-aware; adjust when backend adds folder_id on files
  const visibleFolders = folders; // backend already filters by parent_folder_id
  const visibleFiles = files;     // TODO: filter by folder when supported

  function handleMoveTargetChange(fileId, folderId) {
    setMoveTargets((prev) => ({
      ...prev,
      [fileId]: folderId,
    }));
  }

  async function handleMoveFile(file) {
    const targetFolderId = moveTargets[file.file_id] || null;
    if (!targetFolderId) {
      alert("Please select a folder first");
      return;
    }

    try {
      await moveFile({ fileId: file.file_id, newFolderId: targetFolderId });
      // refresh current view: folders and files
      await refreshFolders(currentFolderId);
      const updatedFiles = await listFiles();
      setFiles(updatedFiles);
      alert("File moved successfully");
    } catch (err) {
      console.error(err);
      alert(err.message || "Failed to move file");
    }
  }

  async function handleMoveFolder(folder) {
    const targetFolderId = moveTargets[folder.folder_id] || null;
    if (targetFolderId === folder.folder_id) {
      alert("Cannot move a folder into itself");
      return;
    }
    try {
      await moveFolder({
        folderId: folder.folder_id,
        newParentFolderId: targetFolderId,
      });
      await refreshFolders(currentFolderId);
      alert("Folder moved successfully");
    } catch (err) {
      console.error(err);
      alert(err.message || "Failed to move folder");
    }
  }

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
            onClick={goUpOneLevel}
            disabled={isLoading || currentFolderId === null}
          >
            ↑ Up
          </button>
          <button
            className="toolbar-action-btn"
            onClick={() => setIsCreatingFolder(true)}
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
              <th>Name</th>
              <th>Size</th>
              <th>Modified Date</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {visibleFolders.length === 0 && visibleFiles.length === 0 ? (
              <tr>
                <td colSpan={4} style={{ textAlign: "center" }}>
                  No items found
                </td>
              </tr>
            ) : (
              <>
                {/* Folders */}
                {visibleFolders.map((folder) => (
                  <tr
                    key={folder.folder_id}
                    className="folder-row"
                    draggable
                    onDragStart={(e) => {
                      e.stopPropagation();
                      setDragItem({ type: "folder", id: folder.folder_id });
                    }}
                    onDragEnd={() => setDragItem(null)}
                    onDragOver={(e) => {
                      // allow dropping other items on this folder
                      e.preventDefault();
                    }}
                    onDrop={async (e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      if (!dragItem) return;

                      try {
                        if (dragItem.type === "file") {
                          await moveFile({
                            fileId: dragItem.id,
                            newFolderId: folder.folder_id,
                          });
                          const updatedFiles = await listFiles();
                          setFiles(updatedFiles);
                        } else if (dragItem.type === "folder") {
                          await moveFolder({
                            folderId: dragItem.id,
                            newParentFolderId: folder.folder_id,
                          });
                          await refreshFolders(currentFolderId);
                        }
                      } catch (err) {
                        console.error(err);
                        alert(err.message || "Failed to move item");
                      } finally {
                        setDragItem(null);
                      }
                    }}
                    onClick={() => enterFolder(folder)}
                    style={{ cursor: "pointer" }}
                  >
                    <td>📁 {folder.name}</td>
                    <td>Folder</td>
                    <td>{new Date(folder.created_at).toLocaleString()}</td>
                    <td
                      className="table-actions-cell"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <div className="actions-menu-wrapper">
                        <button
                          type="button"
                          className="table-action-trigger"
                          onClick={() => toggleMenu(folder.folder_id)}
                        >
                          ⋮
                        </button>

                        {openMenuFileId === folder.folder_id && (
                          <div className="actions-menu-dropdown">
                            <button
                              type="button"
                              className="actions-menu-item"
                              onClick={() => {
                                closeMenu();
                                alert("Folder delete not implemented yet");
                              }}
                            >
                              Delete
                            </button>

                            <div className="actions-menu-item">
                              <select
                                className="search-input"
                                value={moveTargets[folder.folder_id] || ""}
                                onChange={(e) =>
                                  handleMoveTargetChange(
                                    folder.folder_id,
                                    e.target.value
                                  )
                                }
                              >
                                <option value="">Move to folder…</option>
                                {folders
                                  .filter(
                                    (f) => f.folder_id !== folder.folder_id
                                  )
                                  .map((f) => (
                                    <option
                                      key={f.folder_id}
                                      value={f.folder_id}
                                    >
                                      {f.name}
                                    </option>
                                  ))}
                              </select>
                              <button
                                type="button"
                                className="table-action-trigger"
                                style={{ marginLeft: 4 }}
                                onClick={() => {
                                  closeMenu();
                                  handleMoveFolder(folder);
                                }}
                              >
                                Move
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}

                {/* Files */}
                {visibleFiles.length === 0 ? (
                  <tr>
                    <td colSpan={4} style={{ textAlign: "center" }}>
                      No files found
                    </td>
                  </tr>
                ) : (
                  visibleFiles.map((file) => (
                    <tr
                      key={file.file_id}
                      draggable
                      onDragStart={() =>
                        setDragItem({ type: "file", id: file.file_id })
                      }
                      onDragEnd={() => setDragItem(null)}
                    >
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
                                  alert("Delete not implemented yet");
                                }}
                              >
                                Delete
                              </button>

                              <div className="actions-menu-item">
                                <select
                                  className="search-input"
                                  value={moveTargets[file.file_id] || ""}
                                  onChange={(e) =>
                                    handleMoveTargetChange(
                                      file.file_id,
                                      e.target.value
                                    )
                                  }
                                >
                                  <option value="">Select folder</option>
                                  {folders.map((folder) => (
                                    <option
                                      key={folder.folder_id}
                                      value={folder.folder_id}
                                    >
                                      {folder.name}
                                    </option>
                                  ))}
                                </select>
                                <button
                                  type="button"
                                  className="table-action-trigger"
                                  style={{ marginLeft: 4 }}
                                  onClick={() => {
                                    closeMenu();
                                    handleMoveFile(file);
                                  }}
                                >
                                  Move
                                </button>
                              </div>

                              <button
                                type="button"
                                className="actions-menu-item"
                                onClick={() => {
                                  closeMenu();
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
              </>
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
