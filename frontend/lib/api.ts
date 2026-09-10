import type {
  Analytics,
  AuthStatus,
  CallLog,
  ConfigCheck,
  IntakeReply,
  ScheduleResponse,
  SyncReport,
  Task,
  TaskStatus,
} from "./types";

export const API_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  retryAfterSeconds?: number;

  constructor(status: number, message: string, retryAfterSeconds?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.retryAfterSeconds = retryAfterSeconds;
  }

  /** The session cookie is missing or invalid — the user needs to reconnect. */
  get isUnauthenticated() {
    return this.status === 401;
  }

  get isRateLimited() {
    return this.status === 429;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${API_URL}${path}`, {
      // The backend authenticates with an HttpOnly cookie, so every call must
      // send credentials — without this each request looks anonymous.
      credentials: "include",
      ...init,
      headers: {
        ...(init.body && !(init.body instanceof FormData)
          ? { "Content-Type": "application/json" }
          : {}),
        ...init.headers,
      },
    });
  } catch {
    throw new ApiError(
      0,
      `Can't reach the API at ${API_URL}. Is the backend running? (docker compose up)`,
    );
  }

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") {
        detail = body.detail;
      } else if (Array.isArray(body?.detail)) {
        // FastAPI validation errors arrive as a list.
        detail = body.detail
          .map((d: { loc?: string[]; msg?: string }) =>
            [d.loc?.slice(1).join("."), d.msg].filter(Boolean).join(": "),
          )
          .join("; ");
      }
    } catch {
      /* keep the status line */
    }

    const retryAfter = response.headers.get("Retry-After");
    throw new ApiError(
      response.status,
      detail,
      retryAfter ? Number(retryAfter) : undefined,
    );
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const json = (body: unknown) => JSON.stringify(body);

export const api = {
  // --- auth ---
  authStatus: () => request<AuthStatus>("/auth/google/status"),
  configCheck: () => request<ConfigCheck>("/config-check"),
  loginUrl: () => `${API_URL}/auth/google/login`,
  logout: () => request<unknown>("/auth/google/logout", { method: "POST" }),

  // --- goals ---
  intake: (messages: { role: string; content: string }[]) =>
    request<IntakeReply>("/goals/intake", {
      method: "POST",
      body: json({ messages }),
    }),

  schedule: (body: {
    goal: string;
    horizon_days: number;
    daily_hours: number;
    context?: string;
    holidays?: string[];
  }) =>
    request<ScheduleResponse>("/goals/schedule", {
      method: "POST",
      body: json(body),
    }),

  // --- tasks ---
  tasks: (status?: TaskStatus) =>
    request<{ tasks: Task[] }>(`/tasks${status ? `?status=${status}` : ""}`),

  setTaskStatus: (id: number, status: TaskStatus, progressNote?: string) =>
    request<{ id: number; title: string; status: TaskStatus }>(`/tasks/${id}`, {
      method: "PATCH",
      body: json({ status, progress_note: progressNote ?? null }),
    }),

  syncCalendar: () => request<SyncReport>("/tasks/sync", { method: "POST" }),

  rescheduleTask: (id: number, start: string, end: string) =>
    request<{ id: number; scheduled_start: string; scheduled_end: string }>(
      `/tasks/${id}/reschedule`,
      { method: "PATCH", body: json({ start, end }) },
    ),

  deleteTask: (id: number) =>
    request<{ deleted: number; calendar_event_removed: boolean }>(
      `/tasks/${id}`,
      { method: "DELETE" },
    ),

  registerPhone: (body: {
    phone: string;
    name?: string;
    daily_checkin_enabled: boolean;
    preferred_checkin_hour: number;
    timezone: string;
  }) => request<unknown>("/tasks/register-phone", { method: "POST", body: json(body) }),

  // --- analytics & calls ---
  analytics: () => request<Analytics>("/analytics"),
  callHistory: () => request<{ calls: CallLog[] }>("/calls/history"),
  triggerCall: () =>
    request<{ message: string; call_sid: string; call_log_id: number }>(
      "/calls/trigger",
      { method: "POST" },
    ),

  // --- chat & voice ---
  chat: (message: string, history: { role: string; content: string }[]) =>
    request<{ reply: string }>("/chat", {
      method: "POST",
      body: json({ message, history }),
    }),

  transcribe: (audio: Blob, filename = "recording.webm") => {
    const form = new FormData();
    form.append("audio", audio, filename);
    return request<{ text: string }>("/voice/transcribe", {
      method: "POST",
      body: form,
    });
  },
};
