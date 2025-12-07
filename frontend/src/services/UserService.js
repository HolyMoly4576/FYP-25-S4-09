const API_BASE_URL = "http://localhost:8004";  
const TOKEN_KEY = "accessToken";
const USER_KEY = "user";

// ---------- Token + user helpers ----------
export function getAccessToken() {
  return localStorage.getItem(TOKEN_KEY) || null;
}

export function setAccessToken(token) {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
}

export function setCurrentUser(user) {
  if (user) {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  } else {
    localStorage.removeItem(USER_KEY);
  }
}

export function getCurrentUser() {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

// central logout
export function logout() {
  clearAuth();
  window.location.href = "/"; // or use react-router navigation
}

// generic request wrapper
async function authFetch(url, options = {}) {
  const token = getAccessToken();

  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(url, { ...options, headers });

  if (response.status === 401) {
    // token invalid or expired -> force logout
    logout();
    throw new Error("Session expired. Please log in again.");
  }

  return response;
}

// ---------- File upload ----------
export async function uploadFile({ file, folderId = null, erasureId = "MEDIUM" }) {
  const toBase64 = (file) =>
    new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = reader.result;
        const base64 = result.split(",")[1];
        resolve(base64);
      };
      reader.onerror = (err) => reject(err);
      reader.readAsDataURL(file);
    });

  const base64Data = await toBase64(file);

  const payload = {
    filename: file.name,
    data: base64Data,
    content_type: file.type || "application/octet-stream",
    folder_id: folderId,
    erasure_id: erasureId, // this will be LOW/MEDIUM/HIGH from UI
  };

  const response = await authFetch(`${API_BASE_URL}/files/upload`, {
    method: "POST",
    body: JSON.stringify(payload),
  });

  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.detail || result.message || "Failed to upload file");
  }
  return result;
}

// ---------- File list ----------
export async function listFiles() {
  const response = await authFetch(`${API_BASE_URL}/files/list`, {
    method: "GET",
  });

  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.detail || result.message || "Failed to list files");
  }

  // Backend returns { files: [...] } matching FileListResponse
  return result.files || [];
}

// ---------- File download ----------
export async function downloadFile(fileId, fileName) {
  const token = getAccessToken();
  if (!token) {
    throw new Error("Not authenticated");
  }

  const response = await fetch(`${API_BASE_URL}/files/download/${fileId}`, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "Failed to download file");
  }

  // Response is raw bytes with Content-Disposition header
  const blob = await response.blob();

  // Try to extract filename from Content-Disposition; fall back to provided name
  const disposition = response.headers.get("Content-Disposition");
  let downloadName = fileName || "download";
  if (disposition) {
    const match = disposition.match(/filename="?([^"]+)"?/i);
    if (match && match[1]) {
      downloadName = match[1];
    }
  }

  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = downloadName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

// ---------- File info ----------
export async function getFileInfo(fileId) {
  const response = await authFetch(`${API_BASE_URL}/files/info/${fileId}`, {
    method: "GET",
  });

  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.detail || result.message || "Failed to get file info");
  }

  // Backend returns a single FileInfo object
  return result;
}

// ---------- File search ----------
export async function searchFiles(query) {
  const params = new URLSearchParams({ q: query });
  const response = await authFetch(
    `${API_BASE_URL}/files/search?${params.toString()}`,
    { method: "GET" }
  );

  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.detail || result.message || "Failed to search files");
  }

  // Backend returns { files: [...], total: number }
  return result.files || [];
}

// ---------- Folders ----------
export async function createFolder({ name, parentFolderId = null }) {
  const token = getAccessToken();
  if (!token) {
    throw new Error("Not authenticated");
  }

  const response = await authFetch(`${API_BASE_URL}/folders`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      name,
      parent_folder_id: parentFolderId, // backend expects this field name
    }),
  });

  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.detail || result.message || "Failed to create folder");
  }

  return result;
}

// ---------- Storage usage ----------
export async function getStorageUsage() {
  const token = getAccessToken();
  if (!token) {
    throw new Error("Not authenticated");
  }

  const response = await authFetch(`${API_BASE_URL}/storage/usage`, {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
  });

  const result = await response.json();
  if (!response.ok) {
    throw new Error(
      result.detail || result.message || "Failed to fetch storage usage"
    );
  }

  return result;
}
