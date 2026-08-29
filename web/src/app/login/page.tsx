"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, setSession } from "@/lib/api";
import { notifySession, useAsyncAction } from "@/lib/hooks";
import { Button, ErrorNote } from "@/components/ui";

function LoginForm() {
  const params = useSearchParams();
  const router = useRouter();
  const [email, setEmail] = useState("admin@sentinel.local");
  const [password, setPassword] = useState("admin12345");
  const { busy, error, run } = useAsyncAction();
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const out = await run(() => api.login(email, password));
    if (out) {
      setSession(out.access_token, { email: out.email, role: out.role, user_id: out.user_id });
      notifySession();
      const next = params.get("next") ?? "/";
      router.push(next.startsWith("/") ? next : "/");
    }
  };
  return (
    <form onSubmit={submit} className="panel w-full max-w-sm space-y-4 p-6">
      <div>
        <div className="flex items-center gap-2">
          <span className="grid h-8 w-8 place-items-center rounded-md bg-accent/15 text-accent">◆</span>
          <div>
            <div className="text-base font-semibold tracking-wide">SENTINEL</div>
            <div className="text-[10px] uppercase tracking-[0.16em] text-fg-dim">evidence-driven incident intelligence</div>
          </div>
        </div>
      </div>
      <label className="block text-xs text-fg-muted">
        Email
        <input value={email} onChange={(e) => setEmail(e.target.value)} className="mt-1 w-full rounded-md border border-border bg-bg px-3 py-2 text-sm text-fg outline-none focus:border-accent" autoComplete="username" />
      </label>
      <label className="block text-xs text-fg-muted">
        Password
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} className="mt-1 w-full rounded-md border border-border bg-bg px-3 py-2 text-sm text-fg outline-none focus:border-accent" autoComplete="current-password" />
      </label>
      {error && <ErrorNote>{error}</ErrorNote>}
      <Button type="submit" variant="primary" disabled={busy} className="w-full justify-center py-2">
        {busy ? "Signing in…" : "Sign in"}
      </Button>
      <p className="text-center text-[11px] text-fg-dim">Local deployment · bootstrap admin credentials are in <span className="mono">.env.example</span></p>
    </form>
  );
}

export default function LoginPage() {
  return (
    <div className="grid min-h-screen place-items-center px-4">
      <Suspense fallback={null}>
        <LoginForm />
      </Suspense>
    </div>
  );
}
