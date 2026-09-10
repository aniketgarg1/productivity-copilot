"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import { formatMinutes, parseServerDate, startOfWeek } from "@/lib/format";
import type { Task } from "@/lib/types";
import { Shell } from "@/components/Shell";
import { EmptyState, ErrorBanner, Loading, PageHeading } from "@/components/ui";
import { ChevronLeftIcon, ChevronRightIcon, SyncIcon } from "@/components/Icons";

const DAY_START_HOUR = 8;
const DAY_END_HOUR = 19;
const ROW_HEIGHT = 56; // px per hour — event geometry depends on this
const HOURS = Array.from({ length: DAY_END_HOUR - DAY_START_HOUR }, (_, i) => DAY_START_HOUR + i);

export default function CalendarPage() {
  const [tasks, setTasks] = useState<Task[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date()));
  const [syncing, setSyncing] = useState(false);
  // "Now" only exists on the client. Reading the clock during render makes the
  // server and client markup disagree, which fails hydration.
  const [now, setNow] = useState<Date | null>(null);

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

  useEffect(() => {
    setNow(new Date());
    const id = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(id);
  }, []);

  async function runSync() {
    setSyncing(true);
    try {
      await api.syncCalendar();
      await load();
    } catch (e) {
      setError(e);
    } finally {
      setSyncing(false);
    }
  }

  const days = useMemo(
    () =>
      Array.from({ length: 7 }, (_, i) => {
        const d = new Date(weekStart);
        d.setDate(d.getDate() + i);
        return d;
      }),
    [weekStart],
  );

  const scheduled = useMemo(
    () =>
      (tasks ?? [])
        .map((task) => ({ task, start: parseServerDate(task.scheduled_start), end: parseServerDate(task.scheduled_end) }))
        .filter((x): x is { task: Task; start: Date; end: Date } => !!x.start && !!x.end),
    [tasks],
  );

  const weekEnd = useMemo(() => {
    const d = new Date(weekStart);
    d.setDate(d.getDate() + 7);
    return d;
  }, [weekStart]);

  const inWeek = scheduled.filter((s) => s.start >= weekStart && s.start < weekEnd);
  const bookedMinutes = inWeek.reduce((sum, s) => sum + s.task.estimate_minutes, 0);

  const nowOffset = now
    ? (now.getHours() + now.getMinutes() / 60 - DAY_START_HOUR) * ROW_HEIGHT
    : -1;

  function shiftWeek(delta: number) {
    const next = new Date(weekStart);
    next.setDate(next.getDate() + delta * 7);
    setWeekStart(next);
  }

  const rangeLabel = `${days[0].toLocaleDateString(undefined, { day: "numeric", month: "short" })} – ${days[6].toLocaleDateString(undefined, { day: "numeric", month: "short" })}`;

  return (
    <Shell>
      <PageHeading
        title="This week"
        subtitle={
          <span className="mono">
            {rangeLabel} · {formatMinutes(bookedMinutes)} scheduled
          </span>
        }
        actions={
          <>
            <button className="btn" onClick={runSync} disabled={syncing}>
              {syncing ? <span className="spinner" /> : <SyncIcon stroke="var(--muted)" />}
              Sync
            </button>
            <button className="btn" onClick={() => shiftWeek(-1)} aria-label="Previous week">
              <ChevronLeftIcon stroke="var(--muted)" />
            </button>
            <button className="btn" onClick={() => setWeekStart(startOfWeek(new Date()))}>
              Today
            </button>
            <button className="btn" onClick={() => shiftWeek(1)} aria-label="Next week">
              <ChevronRightIcon stroke="var(--muted)" />
            </button>
          </>
        }
      />

      <ErrorBanner error={error} />

      {tasks === null ? (
        <Loading label="Loading your week…" />
      ) : inWeek.length === 0 && scheduled.length === 0 ? (
        <EmptyState
          title="Nothing scheduled"
          body="Once you build a roadmap, the tasks Copilot books show up here alongside the free time it found."
        />
      ) : (
        <div className="card" style={{ overflow: "hidden" }}>
          <div style={{ overflowX: "auto" }}>
            <div style={{ minWidth: 760 }}>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: `58px repeat(7, minmax(0, 1fr))`,
                  borderBottom: "1px solid var(--rule)",
                  background: "var(--surface-alt)",
                }}
              >
                <div />
                {days.map((day) => {
                  const isToday = !!now && day.toDateString() === now.toDateString();
                  return (
                    <div
                      key={day.toISOString()}
                      style={{
                        padding: "11px 8px",
                        textAlign: "center",
                        borderLeft: "1px solid var(--rule-soft)",
                        background: isToday ? "#f7f0e9" : undefined,
                      }}
                    >
                      <div
                        className="eyebrow"
                        style={{ color: isToday ? "var(--accent)" : undefined, fontWeight: isToday ? 600 : 500 }}
                      >
                        {day.toLocaleDateString(undefined, { weekday: "short" })}
                      </div>
                      <div
                        className="mono"
                        style={{ fontSize: 15, marginTop: 2, color: isToday ? "var(--accent)" : "var(--muted)" }}
                      >
                        {day.getDate()}
                      </div>
                    </div>
                  );
                })}
              </div>

              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: `58px repeat(7, minmax(0, 1fr))`,
                  position: "relative",
                }}
              >
                <div>
                  {HOURS.map((hour, i) => (
                    <div
                      key={hour}
                      style={{
                        height: ROW_HEIGHT,
                        borderTop: i === 0 ? "none" : "1px solid var(--rule-soft)",
                        position: "relative",
                      }}
                    >
                      <span
                        className="mono"
                        style={{ position: "absolute", top: -7, right: 9, fontSize: 11, color: "var(--ghost)" }}
                      >
                        {String(hour).padStart(2, "0")}:00
                      </span>
                    </div>
                  ))}
                </div>

                {days.map((day) => {
                  const isToday = !!now && day.toDateString() === now.toDateString();
                  const dayEvents = scheduled.filter(
                    (s) => s.start.toDateString() === day.toDateString(),
                  );

                  return (
                    <div
                      key={day.toISOString()}
                      style={{
                        position: "relative",
                        borderLeft: "1px solid var(--rule-soft)",
                        background: isToday ? "#fdfaf6" : undefined,
                      }}
                    >
                      {HOURS.map((hour, i) => (
                        <div
                          key={hour}
                          style={{
                            height: ROW_HEIGHT,
                            borderTop: i === 0 ? "none" : "1px solid var(--rule-soft)",
                          }}
                        />
                      ))}

                      {dayEvents.map(({ task, start, end }) => {
                        const top =
                          (start.getHours() + start.getMinutes() / 60 - DAY_START_HOUR) * ROW_HEIGHT;
                        const height = Math.max(
                          22,
                          ((end.getTime() - start.getTime()) / 3_600_000) * ROW_HEIGHT,
                        );
                        if (top + height < 0 || top > HOURS.length * ROW_HEIGHT) return null;

                        const done = task.status === "done";
                        const active = task.status === "in_progress";

                        return (
                          <div
                            key={task.id}
                            title={`${task.title} · ${formatMinutes(task.estimate_minutes)}`}
                            style={{
                              position: "absolute",
                              top: Math.max(0, top),
                              height,
                              left: 3,
                              right: 3,
                              borderRadius: 5,
                              padding: "5px 7px",
                              overflow: "hidden",
                              background: done
                                ? "var(--positive-soft)"
                                : active
                                  ? "var(--accent)"
                                  : "var(--accent-soft)",
                              borderLeft: `3px solid ${done ? "var(--positive)" : "var(--accent-dark)"}`,
                            }}
                          >
                            <div
                              style={{
                                fontSize: 11.5,
                                fontWeight: 500,
                                lineHeight: 1.25,
                                color: done
                                  ? "var(--positive)"
                                  : active
                                    ? "#fff"
                                    : "var(--accent-dark)",
                                textDecoration: done ? "line-through" : "none",
                              }}
                            >
                              {task.title}
                            </div>
                            {height >= 40 ? (
                              <div
                                className="mono"
                                style={{
                                  fontSize: 10.5,
                                  marginTop: 2,
                                  color: done ? "#6f9a83" : active ? "#f0d9cf" : "var(--accent)",
                                }}
                              >
                                {start.toLocaleTimeString(undefined, {
                                  hour: "2-digit",
                                  minute: "2-digit",
                                  hour12: false,
                                })}
                              </div>
                            ) : null}
                          </div>
                        );
                      })}

                      {isToday && nowOffset >= 0 && nowOffset <= HOURS.length * ROW_HEIGHT ? (
                        <div
                          style={{
                            position: "absolute",
                            top: nowOffset,
                            left: 0,
                            right: 0,
                            borderTop: "1.5px solid var(--accent)",
                            zIndex: 3,
                          }}
                        >
                          <span
                            style={{
                              position: "absolute",
                              left: -3,
                              top: -4,
                              width: 7,
                              height: 7,
                              borderRadius: "50%",
                              background: "var(--accent)",
                            }}
                          />
                        </div>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      )}

      <p style={{ margin: 0, fontSize: 12.5, color: "var(--faint)", textWrap: "pretty" }}>
        Only Copilot tasks are shown. Your other calendar events aren&apos;t displayed, but the
        scheduler works around them — it books into free time only.
      </p>
    </Shell>
  );
}
