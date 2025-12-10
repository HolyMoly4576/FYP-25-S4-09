import { API_BASE_URL, authFetch } from "./UserService";

// List items in recycle bin
export async function listBinItems() {
  const response = await authFetch(`${API_BASE_URL}/bin/list`, {
    method: "GET",
  });

  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.detail || result.message || "Failed to load recycle bin");
  }
  return result; // Array<BinItemResponse>
}

// Get bin statistics
export async function getBinStats() {
  const response = await authFetch(`${API_BASE_URL}/bin/stats`, {
    method: "GET",
  });

  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.detail || result.message || "Failed to load recycle bin stats");
  }
  return result;
}

// Restore one item
export async function restoreBinItem(binId) {
  const response = await authFetch(`${API_BASE_URL}/bin/restore`, {
    method: "POST",
    body: JSON.stringify({ bin_id: binId }),
  });

  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.detail || result.message || "Failed to restore item");
  }
  return result;
}

// Empty whole bin
export async function emptyBin() {
  const response = await authFetch(`${API_BASE_URL}/bin/empty`, {
    method: "DELETE",
  });

  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.detail || result.message || "Failed to empty recycle bin");
  }
  return result;
}

// Permanently delete one bin item
export async function permanentDeleteBinItem(binId) {
  const response = await authFetch(`${API_BASE_URL}/bin/permanent-delete/${binId}`, {
    method: "DELETE",
  });

  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.detail || result.message || "Failed to permanently delete item");
  }
  return result;
}