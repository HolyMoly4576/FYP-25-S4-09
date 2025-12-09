import { API_BASE_URL, authFetch } from "./UserService";

export async function upgradeAccount(monthlyCost) {
  const res = await authFetch(`${API_BASE_URL}/account/upgrade`, {
    method: "POST",
    body: JSON.stringify({ monthly_cost: monthlyCost }),
  });

  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || "Failed to upgrade account");
  }

  return res.json();
}

export async function downgradeAccount() {
  const res = await authFetch(`${API_BASE_URL}/account/downgrade`, {
    method: "POST",
    body: JSON.stringify({ confirm: true }),
  });

  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || "Failed to downgrade account");
  }

  return res.json();
}