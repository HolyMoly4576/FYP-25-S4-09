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

// ---------- File upload ----------
export async function uploadFile({ file, folderId = null, erasureId = "MEDIUM" }) {
  const token = getAccessToken();
  if (!token) {
    throw new Error("Not authenticated");
  }

  // convert File -> base64 (no data:... prefix)
  const toBase64 = (file) =>
    new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        // reader.result is like "data:<mime>;base64,AAAA..."
        const result = reader.result;
        const base64 = result.split(",")[1]; // keep only the base64 part
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
    erasure_id: erasureId,
  };

  const response = await fetch(`${API_BASE_URL}/files/upload`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });

  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.detail || result.message || "Failed to upload file");
  }

  return result; // matches FileUploadResponse
}

// ---------- Folders ----------
export async function createFolder({ name, parentFolderId = null }) {
  const token = getAccessToken();
  if (!token) {
    throw new Error("Not authenticated");
  }

  const response = await fetch(`${API_BASE_URL}/folders`, {
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

  const response = await fetch(`${API_BASE_URL}/storage/usage`, {
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
