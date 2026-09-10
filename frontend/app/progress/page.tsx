"use client";

import { useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import { formatMinutes } from "@/lib/format";
import type { Analytics } from "@/lib/types";
import { Shell } from "@/components/Shell";
import { EmptyState, ErrorBanner, Loading, PageHeading } from "@/components/ui";

// Validated categorical palette (see backend/design notes) — these four are
// distinguishable under deuteranopia and protanopia, and every segment also
// carries a text label so identity is never colour-alone.
const STATUS_COLORS = {
  done: "var(--st-done)",
  in_progress: "var(--st-progress)",
  pending: "var(--st-pending)",
  skipped: "var(--st-skipped)",
} as const;

export default function ProgressPage() {
  const [data, setData] = useState<Analytics | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    api.analytics().then(setData).catch(setError);
  }, []);

  const maxCount = useMemo(
    () => Math.max(1, ...(data?.daily_completions ?? []).map((d) => d.count)),
    [data],
  );

  if (error) {
    return (
      <Shell>
        <PageHeading title="Progress" />
        <ErrorBanner error={error} />
      </Shell>
    );
  }

  if (!data) {
    return (
      <Shell>
        <PageHeading title="Progress" />
        <Loading label="Crunching your numbers…" />
      </Shell>
    );
  }

  if (data.total_tasks === 0) {
    return (
      <Shell>
        <PageHeading title="Progress" />
        <EmptyState
          title="Nothing to measure yet"
          body="Once you've scheduled a goal and started ticking tasks off, your streak, completion rate and daily history show up here."
        />
      </Shell>
    );
  }

  const segments = [
    { key: "done", label: "Done", count: data.completed },
    { key: "in_progress", label: "In progress", count: data.in_progress },
    { key: "pending", label: "Pending", count: data.pending },
    { key: "skipped", label: "Skipped", count: data.skipped },
  ] as const;

  return (
    <Shell>
      <PageHeading title="Progress" subtitle="Last 30 days, across every goal" />

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 16 }}>
        <Stat
          label="Current streak"
          value={String(data.streak_days)}
          unit={data.streak_days === 1 ? "day" : "days"}
          note={data.streak_days === 0 ? "Finish one task to start one" : "Consecutive days with a task done"}
          accent
        />
        <Stat
          label="Completion rate"
          value={String(Math.round(data.completion_rate))}
          unit="%"
          note={`${data.completed} done of ${data.total_tasks} scheduled`}
        />
        <Stat
          label="Time invested"
          value={
            data.total_completed_minutes < 60
              ? String(data.total_completed_minutes)
              : String(Math.floor(data.total_completed_minutes / 60))
          }
          unit={
            data.total_completed_minutes < 60
              ? "min"
              : `h ${data.total_completed_minutes % 60}m`
          }
          note={`Of ${formatMinutes(data.total_scheduled_minutes)} scheduled`}
        />
        <Stat
          label="Still to do"
          value={String(data.pending + data.in_progress)}
          unit="tasks"
          note={data.skipped ? `${data.skipped} skipped` : "Nothing skipped"}
        />
      </div>

      <section className="card" style={{ padding: "24px 26px 20px", display: "flex", flexDirection: "column", gap: 20 }}>
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
          <h2 style={{ fontSize: 15, fontWeight: 600 }}>Tasks completed per day</h2>
          <span className="mono" style={{ fontSize: 12, color: "var(--faint)" }}>
            last {data.daily_completions.length} days
          </span>
        </div>

        <div
          style={{
            display: "flex",
            alignItems: "flex-end",
            gap: 2,
            height: 112,
            borderBottom: "1px solid var(--rule)",
          }}
        >
          {data.daily_completions.map((day) => (
            <div
              key={day.date}
              title={`${day.date}: ${day.count} task${day.count === 1 ? "" : "s"}`}
              style={{
                flexGrow: 1,
                minWidth: 4,
                height: day.count ? `${(day.count / maxCount) * 96}px` : 3,
                background: day.count ? "var(--accent)" : "var(--rule)",
                borderRadius: day.count ? "3px 3px 0 0" : 2,
                alignSelf: day.count ? undefined : "flex-end",
              }}
            />
          ))}
        </div>

        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span className="mono" style={{ fontSize: 11.5, color: "var(--faint)" }}>
            {data.daily_completions[0]?.date}
          </span>
          <span className="mono" style={{ fontSize: 11.5, color: "var(--accent)", fontWeight: 500 }}>
            today
          </span>
        </div>
      </section>

      <section className="card" style={{ padding: "24px 26px", display: "flex", flexDirection: "column", gap: 18 }}>
        <h2 style={{ fontSize: 15, fontWeight: 600 }}>Where the {data.total_tasks} tasks stand</h2>

        <div style={{ display: "flex", gap: 2, height: 30, borderRadius: 4, overflow: "hidden" }}>
          {segments
            .filter((s) => s.count > 0)
            .map((s) => (
              <div
                key={s.key}
                style={{
                  width: `${(s.count / data.total_tasks) * 100}%`,
                  background: STATUS_COLORS[s.key],
                }}
                title={`${s.label}: ${s.count}`}
              />
            ))}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: "13px 24px" }}>
          {segments.map((s) => (
            <div key={s.key} style={{ display: "flex", alignItems: "center", gap: 9 }}>
              <span
                style={{
                  width: 10,
                  height: 10,
                  borderRadius: 2,
                  background: STATUS_COLORS[s.key],
                  flexShrink: 0,
                }}
              />
              <span style={{ fontSize: 13.5, flexGrow: 1 }}>{s.label}</span>
              <span className="mono" style={{ fontSize: 13.5, color: "var(--muted)" }}>
                {s.count}
              </span>
            </div>
          ))}
        </div>
      </section>
    </Shell>
  );
}

function Stat({
  label,
  value,
  unit,
  note,
  accent,
}: {
  label: string;
  value: string;
  unit: string;
  note: string;
  accent?: boolean;
}) {
  return (
    <div
      className="tile"
      style={accent ? { borderColor: "#e0cec3", background: "#fdf7f3" } : undefined}
    >
      <span className="eyebrow">{label}</span>
      <div style={{ display: "flex", alignItems: "baseline", gap: 7 }}>
        <span
          className="serif"
          style={{ fontSize: 44, lineHeight: 1, color: accent ? "var(--accent)" : "var(--ink)" }}
        >
          {value}
        </span>
        <span style={{ fontSize: 14, color: accent ? "var(--accent-dark)" : "var(--muted)" }}>
          {unit}
        </span>
      </div>
      <span style={{ fontSize: 12, color: "var(--muted)" }}>{note}</span>
    </div>
  );
}
