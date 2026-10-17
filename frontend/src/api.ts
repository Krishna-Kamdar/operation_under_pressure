const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

export type Status = "open" | "in_progress" | "awaiting_approval" | "resolved" | "closed";
export type Priority = "low" | "medium" | "high" | "urgent";
export type WorkItemType = "incident" | "customer_issue" | "payment" | "compliance" | "task";

export interface User {
  id: string;
  email: string;
  display_name: string;
  team_roles: Record<string, string>;
}

export interface Team {
  id: string;
  name: string;
}

export interface WorkItem {
  id: string;
  title: string;
  description: string;
  item_type: WorkItemType;
  priority: Priority;
  status: Status;
  team_id: string;
  assignee_id: string | null;
  creator_id: string;
  due_at: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface ActivityEvent {
  id: string;
  work_item_id: string;
  actor_id: string;
  event_type: string;
  payload: Record<string, string>;
  created_at: string;
}

export interface Comment {
  id: string;
  work_item_id: string;
  author_id: string;
  body: string;
  created_at: string;
}

export interface ItemList {
  items: WorkItem[];
  next_cursor: string | null;
}

const storage = typeof localStorage === "undefined" ? null : localStorage;
let token = storage?.getItem("ops_access_token") ?? null;

export function isAuthenticated() {
  return Boolean(token);
}

export function setToken(value: string | null) {
  token = value;
  if (value) storage?.setItem("ops_access_token", value);
  else storage?.removeItem("ops_access_token");
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(response.status, body?.detail ?? "Request failed.");
  }
  return response.json() as Promise<T>;
}

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
  }
}

export const api = {
  login: (email: string, password: string) =>
    request<{ access_token: string; user: User }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  me: () => request<User>("/auth/me"),
  teams: () => request<Team[]>("/teams"),
  items: (params: URLSearchParams) => request<ItemList>(`/items?${params}`),
  item: (id: string) => request<WorkItem>(`/items/${id}`),
  activity: (id: string) => request<ActivityEvent[]>(`/items/${id}/activity`),
  createComment: (id: string, body: string) =>
    request<Comment>(`/items/${id}/comments`, { method: "POST", body: JSON.stringify({ body }) }),
  claim: (id: string) => request<WorkItem>(`/items/${id}/claim`, { method: "POST" }),
  unassign: (id: string) => request<WorkItem>(`/items/${id}/unassign`, { method: "POST" }),
  createItem: (input: {
    title: string;
    description: string;
    item_type: WorkItemType;
    priority: Priority;
    team_id: string;
  }) =>
    request<WorkItem>("/items", {
      method: "POST",
      headers: { "Idempotency-Key": crypto.randomUUID() },
      body: JSON.stringify(input),
    }),
  updateItem: (id: string, input: {
    title: string;
    description: string;
    priority: Priority;
    expected_version: number;
  }) =>
    request<WorkItem>(`/items/${id}`, {
      method: "PATCH",
      body: JSON.stringify(input),
    }),
  transition: (id: string, status: Status, expectedVersion: number) =>
    request<WorkItem>(`/items/${id}/transition`, {
      method: "POST",
      body: JSON.stringify({ status, expected_version: expectedVersion }),
    }),
};
