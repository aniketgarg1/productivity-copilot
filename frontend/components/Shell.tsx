"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import type { AuthStatus } from "@/lib/types";
import {
  CalendarIcon,
  ChartIcon,
  FlagIcon,
  PhoneIcon,
} from "@/components/Icons";

const NAV = [
  { href: "/dashboard", label: "Roadmap", Icon: FlagIcon },
  { href: "/calendar", label: "Calendar", Icon: CalendarIcon },
  { href: "/progress", label: "Progress", Icon: ChartIcon },
  { href: "/checkins", label: "Check-ins", Icon: PhoneIcon },
] as const;

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [auth, setAuth] = useState<AuthStatus | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    let cancelled = false;

    api
      .authStatus()
      .then((status) => {
        if (cancelled) return;
        setAuth(status);
        if (!status.connected) router.replace("/");
      })
      .catch((error) => {
        if (cancelled) return;
        // A dead backend shouldn't bounce the user to a login they can't use.
        if (error instanceof ApiError && error.isUnauthenticated) router.replace("/");
      })
      .finally(() => !cancelled && setChecked(true));

    return () => {
      cancelled = true;
    };
  }, [router]);

  return (
    <div className="shell">
      <aside className="sidebar">
        <Link href="/dashboard" className="brand" style={{ color: "var(--ink)" }}>
          Copilot
        </Link>

        <nav className="nav">
          {NAV.map(({ href, label, Icon }) => {
            const active = pathname === href || pathname.startsWith(`${href}/`);
            return (
              <Link
                key={href}
                href={href}
                className="navItem"
                data-active={active}
                aria-current={active ? "page" : undefined}
              >
                <Icon stroke={active ? "var(--accent)" : "var(--muted)"} />
                <span>{label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="sidebarAside" style={{ marginTop: "auto", display: "flex", flexDirection: "column", gap: 14 }}>
          <Link href="/goals/new" className="btn btnPrimary" style={{ justifyContent: "center" }}>
            New goal
          </Link>

          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              paddingTop: 16,
              borderTop: "1px solid var(--rule)",
            }}
          >
            <div
              style={{
                width: 30,
                height: 30,
                borderRadius: "50%",
                background: "#e2d9cd",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 12,
                fontWeight: 600,
                color: "#6b6259",
                flexShrink: 0,
              }}
            >
              {(auth?.email ?? "?").slice(0, 2).toUpperCase()}
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 1, minWidth: 0 }}>
              <span
                style={{
                  fontSize: 12.5,
                  fontWeight: 500,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
                title={auth?.email ?? undefined}
              >
                {auth?.email ?? (checked ? "not connected" : "…")}
              </span>
              <span className="mono" style={{ fontSize: 11, color: "var(--faint)" }}>
                {auth?.connected ? "calendar synced" : "offline"}
              </span>
            </div>
          </div>
        </div>
      </aside>

      <main className="main">{children}</main>
    </div>
  );
}
