"use client";

import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import { relativeTime } from "@/lib/format";
import type { CallLog, ConfigCheck } from "@/lib/types";
import { Shell } from "@/components/Shell";
import { EmptyState, ErrorBanner, Loading, PageHeading } from "@/components/ui";
import { PhoneIcon } from "@/components/Icons";

export default function CheckinsPage() {
  const [calls, setCalls] = useState<CallLog[] | null>(null);
  const [config, setConfig] = useState<ConfigCheck | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [calling, setCalling] = useState(false);
  const [editing, setEditing] = useState(false);

  const load = useCallback(async () => {
    try {
      const [{ calls }, cfg] = await Promise.all([api.callHistory(), api.configCheck()]);
      setCalls(calls);
      setConfig(cfg);
    } catch (e) {
      setError(e);
      setCalls([]);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function callNow() {
    setCalling(true);
    setError(null);
    setNotice(null);
    try {
      await api.triggerCall();
      setNotice("Calling you now — it may take a few seconds to ring.");
      setTimeout(load, 4000);
    } catch (e) {
      // A 409 means the calendar says you're busy; that's information, not failure.
      if (e instanceof ApiError && e.status === 409) setNotice(e.message);
      else setError(e);
    } finally {
      setCalling(false);
    }
  }

  return (
    <Shell>
      <PageHeading
        title="Check-ins"
        subtitle="A short call each morning about the tasks on your plate. Answer or don't — nothing breaks either way."
        actions={
          <>
            <button className="btn" onClick={() => setEditing((v) => !v)}>
              {editing ? "Close" : "Phone settings"}
            </button>
            <button className="btn btnPrimary" onClick={callNow} disabled={calling || !config?.twilio}>
              {calling ? <span className="spinner" /> : <PhoneIcon size={15} stroke="#fff" />}
              Call me now
            </button>
          </>
        }
      />

      <ErrorBanner error={error} />
      {notice ? <div className="banner bannerInfo">{notice}</div> : null}

      {config && !config.twilio ? (
        <div className="banner bannerInfo">
          Twilio isn&apos;t configured, so calls are disabled. Add{" "}
          <code>TWILIO_ACCOUNT_SID</code>, <code>TWILIO_AUTH_TOKEN</code> and{" "}
          <code>TWILIO_PHONE_NUMBER</code> to <code>.env</code> and restart the backend.
        </div>
      ) : null}

      {config?.twilio && !config.twilio_webhooks_reachable ? (
        <div className="banner bannerInfo">
          Calls will be <strong>speak-only</strong>: Twilio can&apos;t reach{" "}
          <code>{"BACKEND_URL"}</code> on localhost, so it can&apos;t hear your reply. Expose the
          backend (e.g. <code>ngrok http 8000</code>) and set <code>BACKEND_URL</code> to that
          address for a two-way conversation.
        </div>
      ) : null}

      {editing ? <PhoneSettings onSaved={() => { setEditing(false); setNotice("Phone settings saved."); }} onError={setError} timezone={config?.timezone ?? "America/Phoenix"} /> : null}

      {calls === null ? (
        <Loading label="Loading your check-ins…" />
      ) : calls.length === 0 ? (
        <EmptyState
          title="No check-ins yet"
          body="Register your number and Copilot will call at your chosen hour each morning — skipping the call if your calendar says you're in a meeting."
          action={
            <button className="btn" onClick={() => setEditing(true)}>
              Add your number
            </button>
          }
        />
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {calls.map((call) => (
            <CallCard key={call.id} call={call} />
          ))}
        </div>
      )}
    </Shell>
  );
}

function CallCard({ call }: { call: CallLog }) {
  const status = call.status.toLowerCase();
  const badge =
    status === "completed" || status === "answered"
      ? "badgeDone"
      : status === "failed" || status === "busy"
        ? "badgeWarn"
        : status === "no-answer"
          ? "badgeWarn"
          : "badgeNeutral";

  return (
    <article className="card" style={{ padding: "20px 24px", display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <span style={{ fontSize: 13.5, fontWeight: 600 }}>{relativeTime(call.created_at) || "just now"}</span>
        <span className={`badge ${badge}`}>{call.status || "initiated"}</span>
      </div>

      <div style={{ borderLeft: "2px solid var(--rule-soft)", paddingLeft: 16, display: "flex", flexDirection: "column", gap: 12 }}>
        {call.ai_message ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span className="eyebrow" style={{ color: "var(--accent)" }}>
              Copilot
            </span>
            <p style={{ margin: 0, fontSize: 14, lineHeight: 1.6, maxWidth: 660, textWrap: "pretty" }}>
              {call.ai_message}
            </p>
          </div>
        ) : null}

        {call.user_response ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span className="eyebrow">You</span>
            <p
              style={{
                margin: 0,
                fontSize: 14,
                lineHeight: 1.6,
                color: "var(--muted)",
                fontStyle: "italic",
                maxWidth: 660,
                textWrap: "pretty",
              }}
            >
              “{call.user_response}”
            </p>
          </div>
        ) : null}
      </div>
    </article>
  );
}

function PhoneSettings({
  onSaved,
  onError,
  timezone,
}: {
  onSaved: () => void;
  onError: (e: unknown) => void;
  timezone: string;
}) {
  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [hour, setHour] = useState(9);
  const [enabled, setEnabled] = useState(true);
  const [saving, setSaving] = useState(false);

  const valid = /^\+[1-9]\d{7,14}$/.test(phone);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await api.registerPhone({
        phone,
        name: name || undefined,
        daily_checkin_enabled: enabled,
        preferred_checkin_hour: hour,
        timezone,
      });
      onSaved();
    } catch (err) {
      onError(err);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="card" onSubmit={save} style={{ padding: "22px 24px", display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 16 }}>
        <div className="field">
          <label className="fieldLabel" htmlFor="phone">
            Phone number (E.164)
          </label>
          <input
            id="phone"
            className="input"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder="+14155551234"
            required
          />
          {phone && !valid ? (
            <span style={{ fontSize: 12, color: "#8c2f25" }}>
              Must start with + and the country code, e.g. +14155551234
            </span>
          ) : null}
        </div>

        <div className="field">
          <label className="fieldLabel" htmlFor="name">
            What should Copilot call you?
          </label>
          <input id="name" className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Aniket" />
        </div>

        <div className="field">
          <label className="fieldLabel" htmlFor="hour">
            Call me at
          </label>
          <select id="hour" className="select" value={hour} onChange={(e) => setHour(Number(e.target.value))}>
            {Array.from({ length: 24 }, (_, h) => (
              <option key={h} value={h}>
                {String(h).padStart(2, "0")}:00
              </option>
            ))}
          </select>
          <span style={{ fontSize: 12, color: "var(--faint)" }}>{timezone}</span>
        </div>
      </div>

      <label style={{ display: "flex", alignItems: "center", gap: 9, fontSize: 13.5 }}>
        <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
        Call me every day
      </label>

      <p style={{ margin: 0, fontSize: 12.5, color: "var(--faint)", lineHeight: 1.55 }}>
        On a Twilio trial account the number has to be verified in the Twilio console first.
      </p>

      <button className="btn btnPrimary" type="submit" disabled={!valid || saving} style={{ alignSelf: "flex-start" }}>
        {saving ? <span className="spinner" /> : null}
        Save
      </button>
    </form>
  );
}
