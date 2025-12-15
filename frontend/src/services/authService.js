import { API_BASE_URL } from "./UserService";

export async function loginUser(credentials) {
    const response = await fetch(`${API_BASE_URL}/auth/login`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(credentials),
    });

    const result = await response.json();

    if (!response.ok) {
        // FastAPI returns errors in 'detail' field, not 'message'
        throw new Error(result.detail || result.message || "Login failed");
    }

    return result;
}

export async function getRoles() {
    // Fetches user profiles for use as roles
    const response = await fetch(`${API_BASE_URL}/userprofiles`, {
        method: "GET",
        headers: {
            "Content-Type": "application/json"
        }
    });
    if (!response.ok) {
        throw new Error("Failed to fetch roles");
    }
    const result = await response.json();
    // Return profile_types only
    return result.profiles.map(profile => profile.profile_type);
}

// Just a test