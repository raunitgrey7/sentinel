"use client";

import type {
  AuditEntry,
  Deployment,
  ErrorCluster,
  EvaluationCase,
  EvaluationRun,
  Evidence,
  Fault,
  FaultCatalog,
  Graph,
  Hypothesis,
  Incident,
  IncidentEvent,
  Investigation,
  Overview,
  Page,
  Postmortem,
  Remediation,
  ServiceHealth,
  Topology,
  WhyAnswer,
} from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const TOKEN_KEY = "sentinel.token";
const USER_KEY = "sentinel.user";

export class ApiError extends Error {
  status: number;
  code: string;
  details?: unknown;
  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function getUser(): { email: string; role: string; user_id: string } | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function setSession(token: string, user: { email: string; role: string; user_id: string }) {
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
    window.localStorage.setItem(USER_KEY, JSON.stringify(user));
  } catch {
    /* storage unavailable */
  }
}

export function clearSession() {
  try {
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem(USER_KEY);
  } catch {
    /* ignore */
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { "content-type": "application/json", ...(init.headers as Record<string, string>) };
  const token = getToken();
  if (token) headers.authorization = `Bearer ${token}`;
  const res = await fetch(`${API_URL}${path}`, { ...init, headers, cache: "no-store" });
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  const body = text ? JSON.parse(text) : null;
  if (!res.ok) {
    if (res.status === 401 && typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      clearSession();
      // hard navigation on auth loss: the app shell must re-evaluate the session
      window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`);
    }
    const err = body?.error ?? {};
    throw new ApiError(res.status, err.code ?? "error", err.message ?? res.statusText, err.details);
  }
  return body as T;
}

const get = <T,>(path: string) => request<T>(path);
const post = <T,>(path: string, body?: unknown) => request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
const del = <T,>(path: string) => request<T>(path, { method: "DELETE" });

export const api = {
  login: (email: string, password: string) => post<{ access_token: string; role: string; user_id: string; email: string }>("/api/v1/auth/login", { email, password }),
  overview: (project = "demo-shop") => get<Overview>(`/api/v1/system/overview?project=${project}`),
  config: () => get<Record<string, unknown>>("/api/v1/system/config"),
  audit: (limit = 50) => get<AuditEntry[]>(`/api/v1/system/audit?limit=${limit}`),
  health: (project = "demo-shop") => get<ServiceHealth[]>(`/api/v1/projects/${project}/health`),
  topology: (project = "demo-shop") => get<Topology>(`/api/v1/projects/${project}/topology`),
  deployments: (project = "demo-shop", limit = 20) => get<Deployment[]>(`/api/v1/projects/${project}/deployments?limit=${limit}`),
  series: (service: string, metric: string, minutes = 30, project = "demo-shop") => get<{ ts: string; value: number }[]>(`/api/v1/projects/${project}/metrics/${service}/${metric}?minutes=${minutes}`),
  incidents: (params: { project?: string; open_only?: boolean; limit?: number; offset?: number; status?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.project) q.set("project", params.project);
    if (params.open_only) q.set("open_only", "true");
    if (params.status) q.set("status", params.status);
    q.set("limit", String(params.limit ?? 50));
    q.set("offset", String(params.offset ?? 0));
    return get<Page<Incident>>(`/api/v1/incidents?${q.toString()}`);
  },
  incident: (id: string) => get<Incident>(`/api/v1/incidents/${id}`),
  timeline: (id: string) => get<IncidentEvent[]>(`/api/v1/incidents/${id}/timeline`),
  evidence: (id: string) => get<Evidence[]>(`/api/v1/incidents/${id}/evidence`),
  hypotheses: (id: string) => get<Hypothesis[]>(`/api/v1/incidents/${id}/hypotheses`),
  clusters: (id: string) => get<ErrorCluster[]>(`/api/v1/incidents/${id}/clusters`),
  investigations: (id: string) => get<Investigation[]>(`/api/v1/incidents/${id}/investigations`),
  graph: (id: string) => get<Graph>(`/api/v1/incidents/${id}/graph`),
  why: (id: string, question: string, hypothesis_id?: string) => post<WhyAnswer>(`/api/v1/incidents/${id}/why`, { question, hypothesis_id }),
  investigate: (id: string) => post<{ queued: boolean }>(`/api/v1/incidents/${id}/investigate`),
  transitions: (id: string) => get<string[]>(`/api/v1/incidents/${id}/transitions`),
  transition: (id: string, status: string, note = "") => post<Incident>(`/api/v1/incidents/${id}/transition`, { status, note }),
  resolve: (id: string, notes = "") => post<Incident>(`/api/v1/incidents/${id}/resolve`, { notes }),
  remediation: (id: string) => get<Remediation[]>(`/api/v1/incidents/${id}/remediation`),
  remediationAction: (id: string, action: string, verb: "request" | "approve" | "reject" | "execute", note = "") =>
    post<Remediation>(`/api/v1/incidents/${id}/remediation/${action}/${verb}`, verb === "execute" ? undefined : { note }),
  postmortem: (id: string) => get<Postmortem>(`/api/v1/incidents/${id}/postmortem`),
  generatePostmortem: (id: string) => post<Postmortem>(`/api/v1/incidents/${id}/postmortem`),
  faultCatalog: () => get<FaultCatalog>("/api/v1/faults/catalog"),
  faults: () => get<Fault[]>("/api/v1/faults"),
  injectFault: (body: { project?: string; target: string; fault: string; duration_s: number; severity: string }) => post<Fault>("/api/v1/faults", { project: "demo-shop", ...body }),
  clearFault: (id: string) => del<Fault>(`/api/v1/faults/${id}`),
  clearFaults: () => del<{ cleared: number }>("/api/v1/faults"),
  evalRuns: () => get<EvaluationRun[]>("/api/v1/evaluation/runs"),
  evalLatest: () => get<EvaluationRun>("/api/v1/evaluation/runs/latest"),
  evalCases: (runId: string) => get<EvaluationCase[]>(`/api/v1/evaluation/runs/${runId}/cases`),
  startEval: (limit?: number) => post<{ queued: boolean }>(`/api/v1/evaluation/runs${limit ? `?limit=${limit}` : ""}`),
};
