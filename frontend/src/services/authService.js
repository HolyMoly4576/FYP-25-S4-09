export async function loginUser(credentials) {
    const response = await fetch("http://localhost:8004/auth/login", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(credentials),
    });

    const result = await response.json();

    if (!response.ok) {
        throw new Error(result.message || "Login failed");
    }

    return result;
}

export async function getRoles() {
    // Fetches user profiles for use as roles
    const response = await fetch("http://localhost:8004/userprofiles", {
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
