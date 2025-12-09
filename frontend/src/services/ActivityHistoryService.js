import { API_BASE_URL, authFetch } from "./UserService";

export async function getActivityHistory({
  dateFilter,
  actionType,
  limit = 50,
  offset = 0,
}) {
  const params = new URLSearchParams();
  params.append("limit", limit);
  params.append("offset", offset);

  if (dateFilter) {
    params.append("date_filter", dateFilter);
  }
  if (actionType) {
    params.append("action_type", actionType);
  }

  const url = `${API_BASE_URL}/activity/history?${params.toString()}`;

  const response = await authFetch(url, {
    method: "GET",
  });

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    try {
      const data = await response.json();
      if (data?.detail) {
        message = data.detail;
      }
    } catch {
      // ignore JSON parse errors
    }
    throw new Error(message);
  }

  const data = await response.json();

  return {
    activities: data.activities || [],
    total: data.total || 0,
    limit: data.limit || limit,
    offset: data.offset || offset,
    date_filter: data.date_filter ?? dateFilter ?? null,
  };
}