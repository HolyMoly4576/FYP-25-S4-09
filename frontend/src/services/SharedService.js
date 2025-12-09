import { API_BASE_URL, authFetch } from "./UserService";

// ---------- Sharing: download a file shared with me ----------
export async function downloadSharedFileByShareId(shareId) {
  const url = `${API_BASE_URL}/shares/${shareId}/download`;

  try {
    // call backend with auth header, but do NOT force JSON
    const response = await authFetch(url, {
      method: "GET",
      // override JSON header, backend should set correct Content-Type
      headers: {
        // no "Content-Type" here; let server decide
      },
    });

    if (!response.ok) {
      throw new Error(`Failed to download file (status ${response.status})`);
    }

    // try to extract filename from Content-Disposition
    let filename = "downloaded-file";
    const disposition = response.headers.get("Content-Disposition");
    if (disposition && disposition.includes("filename=")) {
      try {
        const parts = disposition.split(";");
        const filePart = parts
          .map((p) => p.trim())
          .find((p) => p.toLowerCase().startsWith("filename="));
        if (filePart) {
          filename = filePart.split("=")[1].replace(/(^")|("$)/g, "");
        }
      } catch {
        // ignore and keep default filename
      }
    }

    const blob = await response.blob(); // binary data for file [web:21][web:22]

    const urlObject = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = urlObject;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(urlObject); // cleanup [web:21][web:29]
  } catch (err) {
    console.error("Failed to download shared file", err);
    throw err;
  }
}