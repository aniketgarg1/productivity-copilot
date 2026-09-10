/**
 * The backend stores naive UTC timestamps. Parsing them without a zone marker
 * would make the browser read them as local time and shift every task.
 */
export function parseServerDate(value: string | null): Date | null {
  if (!value) return null;
  const hasZone = /(Z|[+-]\d{2}:?\d{2})$/.test(value);
  const date = new Date(hasZone ? value : `${value}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

const time = new Intl.DateTimeFormat(undefined, {
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

const dayShort = new Intl.DateTimeFormat(undefined, {
  weekday: "short",
  day: "numeric",
  month: "short",
});

const dayLong = new Intl.DateTimeFormat(undefined, {
  weekday: "long",
  day: "numeric",
  month: "long",
});

export const formatTime = (d: Date) => time.format(d);
export const formatDay = (d: Date) => dayShort.format(d);
export const formatDayLong = (d: Date) => dayLong.format(d);

export function formatWhen(value: string | null): string {
  const date = parseServerDate(value);
  if (!date) return "unscheduled";

  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const days = Math.round(
    (new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime() -
      startOfToday.getTime()) /
      86_400_000,
  );

  if (days === 0) return `today ${formatTime(date)}`;
  if (days === 1) return `tomorrow ${formatTime(date)}`;
  if (days === -1) return `yesterday ${formatTime(date)}`;
  return `${formatDay(date)} ${formatTime(date)}`;
}

export function formatMinutes(total: number): string {
  if (total < 60) return `${total}m`;
  const hours = Math.floor(total / 60);
  const minutes = total % 60;
  return minutes ? `${hours}h ${minutes}m` : `${hours}h`;
}

export function relativeTime(value: string | null): string {
  const date = parseServerDate(value);
  if (!date) return "";

  const seconds = Math.round((Date.now() - date.getTime()) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86_400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86_400)}d ago`;
}

/** Local wall-clock ISO string, for inputs the backend reads as naive time. */
export function toLocalIsoString(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}:00`
  );
}

export function startOfWeek(d: Date): Date {
  const copy = new Date(d);
  const weekday = (copy.getDay() + 6) % 7; // Monday-first
  copy.setDate(copy.getDate() - weekday);
  copy.setHours(0, 0, 0, 0);
  return copy;
}
