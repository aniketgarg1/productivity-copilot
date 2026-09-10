"use client";

import { useState } from "react";

import { api } from "@/lib/api";
import { formatMinutes, formatWhen } from "@/lib/format";
import type { Task, TaskStatus } from "@/lib/types";
import {
  CheckCircleIcon,
  CircleIcon,
  ClockIcon,
  SkipIcon,
  TrashIcon,
} from "@/components/Icons";

const NEXT_STATUS: Record<TaskStatus, TaskStatus> = {
  pending: "in_progress",
  in_progress: "done",
  done: "pending",
  skipped: "pending",
};

const STATUS_ICON = {
  done: { Icon: CheckCircleIcon, color: "var(--positive)" },
  in_progress: { Icon: ClockIcon, color: "var(--accent)" },
  skipped: { Icon: SkipIcon, color: "var(--faint)" },
  pending: { Icon: CircleIcon, color: "#cfc7bd" },
} as const;

export function TaskRow({
  task,
  onChanged,
  onError,
}: {
  task: Task;
  onChanged: (task: Task | null) => void;
  onError: (e: unknown) => void;
}) {
  const [busy, setBusy] = useState(false);
  const { Icon, color } = STATUS_ICON[task.status];
  const done = task.status === "done";
  const dropped = task.status === "skipped";

  async function cycleStatus() {
    const next = NEXT_STATUS[task.status];
    setBusy(true);
    // Optimistic: the row is the only thing that changes, and a failure reverts.
    onChanged({ ...task, status: next });
    try {
      await api.setTaskStatus(task.id, next);
    } catch (e) {
      onChanged(task);
      onError(e);
    } finally {
      setBusy(false);
    }
  }

  async function skip() {
    setBusy(true);
    onChanged({ ...task, status: "skipped" });
    try {
      await api.setTaskStatus(task.id, "skipped");
    } catch (e) {
      onChanged(task);
      onError(e);
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!confirm(`Delete “${task.title}” and remove it from your calendar?`)) return;
    setBusy(true);
    try {
      await api.deleteTask(task.id);
      onChanged(null);
    } catch (e) {
      onError(e);
      setBusy(false);
    }
  }

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 14,
        padding: "14px 24px",
        borderBottom: "1px solid var(--rule-hair)",
        background: task.status === "in_progress" ? "var(--surface-alt)" : undefined,
        opacity: busy ? 0.6 : 1,
      }}
    >
      <button
        onClick={cycleStatus}
        disabled={busy}
        title={`Mark as ${NEXT_STATUS[task.status].replace("_", " ")}`}
        aria-label={`Task ${task.title}, currently ${task.status}. Mark as ${NEXT_STATUS[task.status]}.`}
        style={{
          background: "none",
          border: "none",
          // Pad the icon out to a comfortable target — the bare 17px glyph is
          // far too small to hit reliably.
          padding: 7,
          margin: -7,
          borderRadius: "50%",
          cursor: busy ? "wait" : "pointer",
          display: "flex",
          flexShrink: 0,
        }}
      >
        <Icon stroke={color} />
      </button>

      <div style={{ flexGrow: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 3 }}>
        <span
          style={{
            fontSize: 14,
            color: done || dropped ? "var(--faint)" : "var(--ink)",
            textDecoration: done || dropped ? "line-through" : "none",
            fontWeight: task.status === "in_progress" ? 500 : 400,
          }}
        >
          {task.title}
        </span>
        {task.resources.length > 0 ? (
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {task.resources.slice(0, 3).map((r) => (
              <a
                key={r.url}
                href={r.url}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  fontSize: 11.5,
                  border: "1px solid var(--accent-hair)",
                  padding: "2px 8px",
                  borderRadius: 4,
                }}
              >
                {new URL(r.url).hostname.replace(/^www\./, "")}
              </a>
            ))}
          </div>
        ) : null}
      </div>

      <span
        className={task.scheduled_start ? "chip chipNeutral" : "chip chipNeutral"}
        style={{ flexShrink: 0, color: task.scheduled_start ? undefined : "var(--ghost)" }}
      >
        {formatWhen(task.scheduled_start)}
      </span>

      <span
        className="mono"
        style={{ fontSize: 12.5, color: "var(--muted)", width: 52, textAlign: "right", flexShrink: 0 }}
      >
        {formatMinutes(task.estimate_minutes)}
      </span>

      <div style={{ display: "flex", gap: 4, flexShrink: 0 }}>
        {task.status !== "skipped" && task.status !== "done" ? (
          <button
            onClick={skip}
            disabled={busy}
            title="Skip this task"
            aria-label={`Skip ${task.title}`}
            style={iconButton}
          >
            <SkipIcon size={14} stroke="var(--faint)" />
          </button>
        ) : null}
        <button
          onClick={remove}
          disabled={busy}
          title="Delete task and calendar event"
          aria-label={`Delete ${task.title}`}
          style={iconButton}
        >
          <TrashIcon size={14} stroke="var(--faint)" />
        </button>
      </div>
    </div>
  );
}

const iconButton: React.CSSProperties = {
  background: "none",
  border: "1px solid transparent",
  borderRadius: 4,
  padding: 7,
  cursor: "pointer",
  display: "flex",
};
