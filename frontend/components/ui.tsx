"use client";

import { ApiError } from "@/lib/api";

export function ErrorBanner({ error }: { error: unknown }) {
  if (!error) return null;

  const isApi = error instanceof ApiError;
  let text = isApi ? error.message : String((error as Error)?.message ?? error);

  if (isApi && error.isRateLimited) {
    text = error.retryAfterSeconds
      ? `${error.message} (about ${error.retryAfterSeconds}s)`
      : error.message;
  }

  return (
    <div className="banner bannerError" role="alert">
      {text}
    </div>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        color: "var(--muted)",
        fontSize: 13.5,
        padding: "28px 0",
      }}
    >
      <span className="spinner" />
      {label}
    </div>
  );
}

export function EmptyState({
  title,
  body,
  action,
}: {
  title: string;
  body: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="card empty">
      <h2 className="serif" style={{ fontSize: 22 }}>
        {title}
      </h2>
      <p style={{ margin: 0, color: "var(--muted)", lineHeight: 1.6, maxWidth: 460 }}>{body}</p>
      {action}
    </div>
  );
}

export function PageHeading({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <header className="pageHead">
      <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
        <h1 className="serif" style={{ fontSize: 33 }}>
          {title}
        </h1>
        {subtitle ? (
          <div style={{ fontSize: 13.5, color: "var(--muted)" }}>{subtitle}</div>
        ) : null}
      </div>
      {actions ? <div style={{ display: "flex", gap: 10 }}>{actions}</div> : null}
    </header>
  );
}
