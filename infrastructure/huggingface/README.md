---
title: Sentinel API
emoji: 🛰️
colorFrom: gray
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
license: apache-2.0
short_description: Evidence-driven incident investigation platform (demo backend)
---

# Sentinel — demo backend

Live backend for **Sentinel**, an open-source, local-first AI incident investigation &
response platform: it detects incidents in a seven-service demo shop, correlates
metrics/logs/traces/deployments, ranks evidence-backed root causes and proposes
human-approved remediation.

* Dashboard (frontend): see the repository README for the live Vercel link
* Source & docs: https://github.com/raunitgrey7/sentinel
* API docs: `/docs` on this Space
* Demo login: `admin@sentinel.local` / `admin12345` (public demo credentials)

This Space runs the FastAPI backend plus the demo shop simulator in one container
(SQLite, in-process queue, deterministic narrator — no external services, no API keys).
State resets when the Space restarts.
