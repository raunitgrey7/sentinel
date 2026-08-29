"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { api, clearSession } from "@/lib/api";
import { notifySession, usePoll, useSession } from "@/lib/hooks";
import { Dot, cx } from "./ui";

const LINKS = [
  { href: "/", label: "Overview", icon: "◎" },
  { href: "/incidents", label: "Incidents", icon: "⚑" },
  { href: "/services", label: "Services", icon: "⬡" },
  { href: "/chaos", label: "Chaos Lab", icon: "⚡" },
  { href: "/evaluation", label: "Evaluation", icon: "▤" },
];

export function Nav() {
  const path = usePathname();
  const router = useRouter();
  const session = useSession();
  const enabled = session.ready && !!session.token;
  const ov = usePoll(() => api.overview(), 5000, [], enabled);
  const status = ov.data?.status;
  if (path.startsWith("/login")) return null;
  return (
    <aside className="sticky top-0 flex h-screen w-56 shrink-0 flex-col border-r border-border bg-bg-elev px-3 py-4">
      <Link href="/" className="flex items-center gap-2 px-2">
        <span className="grid h-7 w-7 place-items-center rounded-md bg-accent/15 text-accent">◆</span>
        <div>
          <div className="text-sm font-semibold tracking-wide">SENTINEL</div>
          <div className="text-[10px] uppercase tracking-[0.16em] text-fg-dim">incident intelligence</div>
        </div>
      </Link>
      <div className="mt-4 flex items-center gap-2 rounded-md border border-border bg-panel px-2.5 py-2 text-xs">
        <Dot tone={status === "HEALTHY" ? "ok" : status === "DEGRADED" ? "crit" : "muted"} pulse={status === "DEGRADED"} />
        <span className="font-medium">{status ?? "…"}</span>
        <span className="ml-auto mono text-fg-muted">{ov.data ? `${ov.data.open_incidents} open` : ""}</span>
      </div>
      <nav className="mt-4 flex flex-col gap-0.5">
        {LINKS.map((l) => {
          const active = l.href === "/" ? path === "/" : path.startsWith(l.href);
          return (
            <Link key={l.href} href={l.href} className={cx("flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition", active ? "bg-accent-soft text-fg" : "text-fg-muted hover:bg-panel hover:text-fg")}>
              <span className={cx("w-4 text-center text-xs", active ? "text-accent" : "text-fg-dim")}>{l.icon}</span>
              {l.label}
              {l.href === "/incidents" && ov.data && ov.data.open_incidents > 0 && <span className="ml-auto rounded bg-crit/15 px-1.5 text-[10px] text-crit mono">{ov.data.open_incidents}</span>}
              {l.href === "/chaos" && ov.data && ov.data.active_faults > 0 && <span className="ml-auto rounded bg-warn/15 px-1.5 text-[10px] text-warn mono">{ov.data.active_faults}</span>}
            </Link>
          );
        })}
      </nav>
      <div className="mt-auto space-y-2 text-[11px] text-fg-muted">
        {ov.data && (
          <div className="rounded-md border border-border bg-panel px-2.5 py-2">
            <div className="flex justify-between"><span>model</span><span className="mono text-fg">{ov.data.llm.provider === "none" ? "deterministic" : ov.data.llm.model}</span></div>
            <div className="flex justify-between"><span>queue</span><span className="mono text-fg">{ov.data.queue.backend} · {ov.data.queue.depth}</span></div>
            {ov.data.llm.circuit && ov.data.llm.circuit.state !== "closed" && <div className="mt-1 text-warn">circuit {ov.data.llm.circuit.state}</div>}
          </div>
        )}
        <div className="flex items-center justify-between px-1">
          <span className="truncate">{session.user?.email ?? ""}</span>
          <span className="rounded bg-panel-2 px-1 mono">{session.user?.role ?? ""}</span>
        </div>
        <button
          onClick={() => {
            clearSession();
            notifySession();
            router.push("/login");
          }}
          className="w-full rounded-md border border-border px-2 py-1.5 text-left hover:border-border-strong hover:text-fg"
        >
          Sign out
        </button>
        <a href={`${process.env.NEXT_PUBLIC_API_URL}/docs`} target="_blank" rel="noreferrer" className="block px-1 text-fg-dim hover:text-fg">API docs ↗</a>
      </div>
    </aside>
  );
}
