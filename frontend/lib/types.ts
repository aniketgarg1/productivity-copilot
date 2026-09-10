export type TaskStatus = "pending" | "in_progress" | "done" | "skipped";

export interface TaskResource {
  title: string;
  url: string;
  type: string;
}

export interface Task {
  id: number;
  title: string;
  goal: string;
  notes: string | null;
  estimate_minutes: number;
  scheduled_start: string | null;
  scheduled_end: string | null;
  calendar_event_id: string | null;
  status: TaskStatus;
  progress_note: string | null;
  resources: TaskResource[];
  last_synced_at: string | null;
}

export interface RoadmapTask {
  title: string;
  estimate_minutes: number;
  difficulty: "easy" | "medium" | "hard";
  notes: string | null;
  resources: TaskResource[];
}

export interface RoadmapMilestone {
  title: string;
  why_it_matters: string;
  due_in_days: number;
  tasks: RoadmapTask[];
}

export interface Roadmap {
  goal: string;
  time_horizon_days: number;
  milestones: RoadmapMilestone[];
}

export interface CalendarEvent {
  id: string;
  htmlLink: string;
  title: string;
  start: string;
  end: string;
  task_id: string | null;
}

export interface ScheduleResponse {
  roadmap: Roadmap;
  events: CalendarEvent[];
  message: string | null;
}

export interface IntakeReply {
  type: "question" | "ready";
  message?: string;
  summary?: string;
}

export interface Analytics {
  total_tasks: number;
  completed: number;
  in_progress: number;
  pending: number;
  skipped: number;
  completion_rate: number;
  total_scheduled_minutes: number;
  total_completed_minutes: number;
  streak_days: number;
  daily_completions: { date: string; count: number }[];
}

export interface CallLog {
  id: number;
  status: string;
  ai_message: string | null;
  user_response: string | null;
  created_at: string | null;
}

export interface SyncReport {
  checked: number;
  unchanged: number;
  moved: { id: number; title: string; from: string | null; to: string }[];
  removed: { id: number; title: string }[];
  skipped_no_event: number;
  summary: string;
}

export interface AuthStatus {
  connected: boolean;
  email: string | null;
}

export interface ConfigCheck {
  google_oauth: boolean;
  google_redirect_uri: string;
  openai: boolean;
  twilio: boolean;
  twilio_webhooks_reachable: boolean;
  session_secret_is_default: boolean;
  daily_checkin_enabled: boolean;
  timezone: string;
  cors_origins: string[];
}
