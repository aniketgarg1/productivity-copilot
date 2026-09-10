"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import type { ConfigCheck } from "@/lib/types";
import { ErrorBanner } from "@/components/ui";

export default function LandingPage() {
  const router = useRouter();
  const [config, setConfig] = useState<ConfigCheck | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const status = await api.authStatus();
        if (cancelled) return;
        if (status.connected) {
          router.replace("/dashboard");
          return;
        }
        setConfig(await api.configCheck());
      } catch (e) {
        if (!cancelled) setError(e);
      } finally {
        if (!cancelled) setChecking(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [router]);

  const backendDown = error instanceof ApiError && error.status === 0;

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "40px 24px",
      }}
    >
      <div style={{ width: "100%", maxWidth: 560, display: "flex", flexDirection: "column", gap: 26 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <span className="brand" style={{ paddingLeft: 0 }}>
            Copilot
          </span>
          <h1 className="serif" style={{ fontSize: 42, lineHeight: 1.12, textWrap: "pretty" }}>
            Turn a goal into a plan your calendar actually has room for.
          </h1>
          <p style={{ margin: 0, color: "var(--muted)", lineHeight: 1.65, fontSize: 15, maxWidth: 460 }}>
            Copilot asks what you&apos;re trying to do, breaks it into small tasks, and books
            them only in the gaps your calendar says are free.
          </p>
        </div>

        <ErrorBanner error={error} />

        {backendDown ? null : (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <a
              href={api.loginUrl()}
              className="btn btnPrimary"
              style={{ justifyContent: "center", padding: "13px 18px", fontSize: 14.5 }}
            >
              Connect Google Calendar
            </a>
            <p style={{ margin: 0, fontSize: 12.5, color: "var(--faint)", lineHeight: 1.55 }}>
              Copilot reads your free/busy times so it never double-books you, and writes the
              tasks it schedules. You can disconnect at any time.
            </p>
          </div>
        )}

        {!checking && config ? <SetupNotes config={config} /> : null}
      </div>
    </div>
  );
}

function SetupNotes({ config }: { config: ConfigCheck }) {
  const problems: string[] = [];
  if (!config.google_oauth) problems.push("Google OAuth isn't configured — set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env");
  if (!config.openai) problems.push("OPENAI_API_KEY isn't set — planning and chat will fail");
  if (config.session_secret_is_default) problems.push("SESSION_SECRET is still the default, so session cookies are forgeable");

  if (!problems.length) return null;

  return (
    <div className="banner bannerInfo">
      <strong style={{ display: "block", marginBottom: 6, color: "var(--ink)" }}>
        Backend setup is incomplete
      </strong>
      <ul style={{ margin: 0, paddingLeft: 18, display: "flex", flexDirection: "column", gap: 4 }}>
        {problems.map((p) => (
          <li key={p}>{p}</li>
        ))}
      </ul>
    </div>
  );
}
