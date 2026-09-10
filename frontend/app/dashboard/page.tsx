"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import { formatMinutes, relativeTime } from "@/lib/format";
import type { SyncReport, Task } from "@/lib/types";
import { Shell } from "@/components/Shell";
import { TaskRow } from "@/components/TaskRow";
import { EmptyState, ErrorBanner, Loading, PageHeading } from "@/components/ui";
import { SyncIcon } from "@/components/Icons";

export default function DashboardPage() {
  const [tasks, setTasks] = useState<Task[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [sync, setSync] = useState<SyncReport | null>(null);
  const [syncing, setSyncing] = useState(false);

  const load = useCallback(async () => {
    try {
      const { tasks } = await api.tasks();
      setTasks(tasks);
      setError(null);
    } catch (e) {
      setError(e);
      setTasks([]);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function runSync() {
    setSyncing(true);
    setError(null);
    try {
      const report = await api.syncCalendar();
      setSync(report);
      // Times may have moved, so re-read rather than patching locally.
      if (report.moved.length || report.removed.length) await load();
    } catch (e) {
      setError(e);
    } finally {
      setSyncing(false);
    }
  }

  const byGoal = useMemo(() => {
    const groups = new Map<string, Task[]>();
    for (const task of tasks ?? []) {
      const list = groups.get(task.goal) ?? [];
      list.push(task);
      groups.set(task.goal, list);
    }
    return [...groups.entries()];
  }, [tasks]);

  const lastSynced = useMemo(() => {
    const stamps = (tasks ?? []).map((t) => t.last_synced_at).filter(Boolean) as string[];
    return stamps.sort().at(-1) ?? null;
  }, [tasks]);

  return (
    <Shell>
      <PageHeading
        title="Roadmap"
        subtitle={
          tasks?.length
            ? `${tasks.filter((t) => t.status === "done").length} of ${tasks.length} tasks done${
                lastSynced ? ` · synced ${relativeTime(lastSynced)}` : ""
              }`
            : undefined
        }
        actions={
          <>
            <button className="btn" onClick={runSync} disabled={syncing}>
              {syncing ? <span className="spinner" /> : <SyncIcon stroke="var(--muted)" />}
              {syncing ? "Syncing…" : "Sync calendar"}
            </button>
            <Link href="/goals/new" className="btn btnPrimary">
              New goal
            </Link>
          </>
        }
      />

      <ErrorBanner error={error} />

      {sync ? (
        <div
          className={`banner ${sync.moved.length || sync.removed.length ? "bannerOk" : "bannerInfo"}`}
          role="status"
        >
          {sync.summary}
          {sync.removed.length ? (
            <ul style={{ margin: "8px 0 0", paddingLeft: 18 }}>
              {sync.removed.map((r) => (
                <li key={r.id}>
                  <strong>{r.title}</strong> was deleted in Google — it&apos;s still on your list,
                  just unscheduled.
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      {tasks === null ? (
        <Loading label="Loading your tasks…" />
      ) : tasks.length === 0 ? (
        <EmptyState
          title="No plan yet"
          body="Tell Copilot what you're trying to achieve. It'll ask a few questions, build a roadmap, and book the tasks into the gaps in your calendar."
          action={
            <Link href="/goals/new" className="btn btnPrimary">
              Start a goal
            </Link>
          }
        />
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          {byGoal.map(([goal, goalTasks]) => (
            <GoalSection
              key={goal}
              goal={goal}
              tasks={goalTasks}
              onTaskChanged={(id, next) =>
                setTasks((current) =>
                  (current ?? []).flatMap((t) =>
                    t.id === id ? (next ? [next] : []) : [t],
                  ),
                )
              }
              onError={setError}
            />
          ))}
        </div>
      )}
    </Shell>
  );
}

function GoalSection({
  goal,
  tasks,
  onTaskChanged,
  onError,
}: {
  goal: string;
  tasks: Task[];
  onTaskChanged: (id: number, next: Task | null) => void;
  onError: (e: unknown) => void;
}) {
  const done = tasks.filter((t) => t.status === "done").length;
  const percent = tasks.length ? Math.round((done / tasks.length) * 100) : 0;
  const remaining = tasks
    .filter((t) => t.status !== "done" && t.status !== "skipped")
    .reduce((sum, t) => sum + t.estimate_minutes, 0);

  const ordered = [...tasks].sort((a, b) => {
    if (!a.scheduled_start) return 1;
    if (!b.scheduled_start) return -1;
    return a.scheduled_start.localeCompare(b.scheduled_start);
  });

  return (
    <section className="card" style={{ overflow: "hidden" }}>
      <div
        style={{
          padding: "20px 24px",
          borderBottom: "1px solid var(--rule-soft)",
          display: "flex",
          flexDirection: "column",
          gap: 12,
        }}
      >
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 20 }}>
          {/* A goal can be a long paragraph if it came from an intake summary,
              so clamp it rather than letting it dominate the card. */}
          <h2
            className="serif"
            title={goal}
            style={{
              fontSize: 24,
              textWrap: "pretty",
              display: "-webkit-box",
              WebkitLineClamp: 2,
              WebkitBoxOrient: "vertical",
              overflow: "hidden",
              minWidth: 0,
            }}
          >
            {goal}
          </h2>
          <span className="mono" style={{ fontSize: 12.5, color: "var(--faint)", flexShrink: 0 }}>
            {formatMinutes(remaining)} left
          </span>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
            <span style={{ fontSize: 13, color: "var(--muted)" }}>
              {done} of {tasks.length} tasks done
            </span>
            <span className="mono" style={{ fontSize: 13, color: "var(--muted)" }}>
              {percent}%
            </span>
          </div>
          <div className="bar">
            <div className="barFill" style={{ width: `${percent}%` }} />
          </div>
        </div>
      </div>

      <div>
        {ordered.map((task) => (
          <TaskRow
            key={task.id}
            task={task}
            onChanged={(next) => onTaskChanged(task.id, next)}
            onError={onError}
          />
        ))}
      </div>
    </section>
  );
}
