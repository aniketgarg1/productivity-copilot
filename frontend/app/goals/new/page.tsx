"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import type { ScheduleResponse } from "@/lib/types";
import { Shell } from "@/components/Shell";
import { ErrorBanner, PageHeading } from "@/components/ui";
import { ArrowRightIcon, SparkIcon } from "@/components/Icons";
import { VoiceButton } from "@/components/VoiceButton";

interface Message {
  role: "assistant" | "user";
  content: string;
}

const OPENING: Message = {
  role: "assistant",
  content:
    "What's your main goal? Tell me everything — what you want to achieve, and why it matters to you.",
};

export default function NewGoalPage() {
  const router = useRouter();
  const [messages, setMessages] = useState<Message[]>([OPENING]);
  const [draft, setDraft] = useState("");
  const [thinking, setThinking] = useState(false);
  const [summary, setSummary] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);

  const [horizonDays, setHorizonDays] = useState(30);
  const [dailyHours, setDailyHours] = useState(1.5);
  const [goalTitle, setGoalTitle] = useState("");
  const [scheduling, setScheduling] = useState(false);
  const [result, setResult] = useState<ScheduleResponse | null>(null);

  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, thinking, summary]);

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || thinking) return;

    const next: Message[] = [...messages, { role: "user", content: trimmed }];
    setMessages(next);
    setDraft("");
    setThinking(true);
    setError(null);

    try {
      const reply = await api.intake(next.map((m) => ({ role: m.role, content: m.content })));
      if (reply.type === "ready") {
        setSummary(reply.summary ?? "");
        // The goal becomes a heading everywhere, so seed a short title from the
        // first answer rather than storing the whole paragraph.
        setGoalTitle((current) => current || shortTitle(next));
      } else {
        setMessages([...next, { role: "assistant", content: reply.message ?? "" }]);
      }
    } catch (e) {
      setError(e);
      setMessages(messages); // roll back so the user can retry their answer
      setDraft(trimmed);
    } finally {
      setThinking(false);
    }
  }

  async function buildPlan() {
    setScheduling(true);
    setError(null);
    try {
      const goal = goalTitle.trim() || shortTitle(messages);
      const response = await api.schedule({
        goal,
        horizon_days: horizonDays,
        daily_hours: dailyHours,
        context: summary ?? "",
      });
      setResult(response);
    } catch (e) {
      setError(e);
    } finally {
      setScheduling(false);
    }
  }

  if (result) {
    return (
      <Shell>
        <PageHeading
          title="Your plan is booked"
          subtitle={result.message ?? undefined}
          actions={
            <button className="btn btnPrimary" onClick={() => router.push("/dashboard")}>
              Go to roadmap
            </button>
          }
        />
        <ScheduledSummary result={result} />
      </Shell>
    );
  }

  return (
    <Shell>
      <PageHeading
        title="Let's figure out the goal"
        subtitle="A few questions first. The better I understand where you're starting from, the less generic the plan will be."
      />

      <ErrorBanner error={error} />

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 300px", gap: 20, alignItems: "start" }}>
        <section className="card" style={{ display: "flex", flexDirection: "column", overflow: "hidden" }}>
          <div style={{ padding: "26px 28px", display: "flex", flexDirection: "column", gap: 20, minHeight: 380 }}>
            {messages.map((message, i) =>
              message.role === "assistant" ? (
                <div key={i} style={{ display: "flex", gap: 13, alignItems: "flex-start" }}>
                  <Avatar />
                  <p style={bubbleAssistant}>{message.content}</p>
                </div>
              ) : (
                <div key={i} style={{ display: "flex", justifyContent: "flex-end" }}>
                  <p style={bubbleUser}>{message.content}</p>
                </div>
              ),
            )}

            {thinking ? (
              <div style={{ display: "flex", gap: 13, alignItems: "center" }}>
                <Avatar />
                <span style={{ fontSize: 13.5, color: "var(--faint)" }}>thinking…</span>
              </div>
            ) : null}

            {summary ? (
              <div className="banner bannerOk" style={{ marginLeft: 40 }}>
                <strong style={{ display: "block", marginBottom: 4 }}>
                  I&apos;ve got enough to build a plan.
                </strong>
                {summary}
              </div>
            ) : null}

            <div ref={endRef} />
          </div>

          {!summary ? (
            <div
              style={{
                padding: "18px 28px 24px",
                borderTop: "1px solid var(--rule)",
                background: "var(--surface-alt)",
              }}
            >
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  send(draft);
                }}
                style={{ display: "flex", gap: 10, alignItems: "flex-end" }}
              >
                <textarea
                  className="textarea"
                  rows={2}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      send(draft);
                    }
                  }}
                  placeholder="Type your answer…"
                  disabled={thinking}
                  style={{ resize: "vertical" }}
                  aria-label="Your answer"
                />
                <VoiceButton
                  onTranscribed={(text) => setDraft((d) => (d ? `${d} ${text}` : text))}
                  onError={setError}
                  disabled={thinking}
                />
                <button
                  type="submit"
                  className="btn btnPrimary"
                  disabled={thinking || !draft.trim()}
                  aria-label="Send"
                  style={{ padding: "11px 14px" }}
                >
                  <ArrowRightIcon stroke="#fff" />
                </button>
              </form>
              <p style={{ margin: "10px 2px 0", fontSize: 12, color: "var(--faint)" }}>
                Press the mic to answer out loud — it transcribes before sending.
              </p>
            </div>
          ) : null}
        </section>

        <aside className="card" style={{ padding: "22px 24px", display: "flex", flexDirection: "column", gap: 18 }}>
          <div className="eyebrow">Plan settings</div>

          <div className="field">
            <label className="fieldLabel" htmlFor="goalTitle">
              Goal name
            </label>
            <input
              id="goalTitle"
              className="input"
              value={goalTitle}
              onChange={(e) => setGoalTitle(e.target.value)}
              placeholder="Learn Rust"
              maxLength={120}
              disabled={!summary}
            />
            <span style={{ fontSize: 12, color: "var(--faint)" }}>
              Shown as the heading on your roadmap.
            </span>
          </div>

          <div className="field">
            <label className="fieldLabel" htmlFor="horizon">
              Finish within
            </label>
            <select
              id="horizon"
              className="select"
              value={horizonDays}
              onChange={(e) => setHorizonDays(Number(e.target.value))}
            >
              {[7, 14, 30, 60, 90].map((d) => (
                <option key={d} value={d}>
                  {d} days
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label className="fieldLabel" htmlFor="hours">
              Time per day
            </label>
            <select
              id="hours"
              className="select"
              value={dailyHours}
              onChange={(e) => setDailyHours(Number(e.target.value))}
            >
              {[0.5, 1, 1.5, 2, 3, 4].map((h) => (
                <option key={h} value={h}>
                  {h} hour{h === 1 ? "" : "s"}
                </option>
              ))}
            </select>
          </div>

          <p style={{ margin: 0, fontSize: 12.5, color: "var(--muted)", lineHeight: 1.55 }}>
            Copilot only books time your calendar says is free, and never exceeds this daily
            budget.
          </p>

          <button
            className="btn btnPrimary"
            onClick={buildPlan}
            disabled={!summary || scheduling}
            style={{ justifyContent: "center" }}
          >
            {scheduling ? <span className="spinner" /> : null}
            {scheduling ? "Building…" : "Build the roadmap"}
          </button>

          {!summary ? (
            <p style={{ margin: 0, fontSize: 12, color: "var(--faint)", lineHeight: 1.5 }}>
              Unlocks once Copilot knows enough about your goal.
            </p>
          ) : null}
        </aside>
      </div>
    </Shell>
  );
}

/** A short, headline-friendly goal name derived from the first answer. */
function shortTitle(messages: Message[]): string {
  const first = messages.find((m) => m.role === "user")?.content.trim() ?? "";
  if (!first) return "My goal";

  const sentence = first.split(/(?<=[.!?])\s/)[0] ?? first;
  const cleaned = sentence
    .replace(/^(i\s+(want|would like|need|hope|plan)\s+to\s+)/i, "")
    .replace(/\s+/g, " ")
    .trim();

  const title = cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
  return title.length > 90 ? `${title.slice(0, 87).trimEnd()}…` : title || "My goal";
}

function Avatar() {
  return (
    <div
      style={{
        width: 27,
        height: 27,
        borderRadius: "50%",
        background: "var(--accent)",
        flexShrink: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        marginTop: 2,
      }}
    >
      <SparkIcon stroke="#fff" />
    </div>
  );
}

function ScheduledSummary({ result }: { result: ScheduleResponse }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {result.roadmap.milestones.map((milestone, i) => (
        <section key={i} className="card" style={{ overflow: "hidden" }}>
          <div style={{ padding: "20px 24px", borderBottom: "1px solid var(--rule-soft)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 11, marginBottom: 7 }}>
              <span className="mono" style={{ fontSize: 11.5, color: "var(--faint)" }}>
                {String(i + 1).padStart(2, "0")}
              </span>
              <h2 style={{ fontSize: 17, fontWeight: 600 }}>{milestone.title}</h2>
            </div>
            <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.55, color: "var(--muted)", maxWidth: 640 }}>
              {milestone.why_it_matters}
            </p>
          </div>
          <div>
            {milestone.tasks.map((task, j) => (
              <div
                key={j}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 14,
                  padding: "13px 24px",
                  borderBottom: "1px solid var(--rule-hair)",
                }}
              >
                <span style={{ flexGrow: 1, fontSize: 14 }}>{task.title}</span>
                <span className="mono" style={{ fontSize: 12.5, color: "var(--muted)" }}>
                  {task.estimate_minutes}m
                </span>
              </div>
            ))}
          </div>
        </section>
      ))}

      {result.events.length ? (
        <p style={{ margin: 0, fontSize: 12.5, color: "var(--faint)" }}>
          {result.events.length} event(s) added to your Google Calendar.{" "}
          <a href={result.events[0].htmlLink} target="_blank" rel="noopener noreferrer">
            Open the first one
          </a>
        </p>
      ) : null}
    </div>
  );
}

const bubbleAssistant: React.CSSProperties = {
  margin: 0,
  fontSize: 15,
  lineHeight: 1.62,
  maxWidth: 520,
  textWrap: "pretty",
};

const bubbleUser: React.CSSProperties = {
  margin: 0,
  fontSize: 15,
  lineHeight: 1.62,
  background: "var(--sidebar)",
  border: "1px solid var(--rule)",
  padding: "13px 17px",
  borderRadius: "10px 10px 2px 10px",
  maxWidth: 440,
  textWrap: "pretty",
};
