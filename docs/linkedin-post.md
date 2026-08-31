# LinkedIn post (ready to paste)

> **Attach image:** `docs/pitch/assets/incident.jpg` (the root-cause card — the money shot),
> or `docs/pitch/assets/overview.jpg` for the full-dashboard look.
> **Before posting:** replace `https://sentinel-phi-seven-74.vercel.app` with the deployed frontend link.
> Post as: text + 1 image. First line matters most — LinkedIn truncates after ~3 lines.

---

Your monitoring says "payment-service is unhealthy."
It never says **why**. So I built the thing that does — and proves it. 🛰️

Meet **Sentinel** — an open-source, local-first AI incident investigation platform.

At 2:13 PM the payment service starts failing. Latency up, DB connections up, checkouts down. Four dashboards turn red. Sentinel opens ONE incident, walks the dependency graph to the deepest failing service, and answers in under a second:

🔴 Root cause: Database connection-pool exhaustion — 89% confidence
✅ Evidence: pool at 40/40 (baseline 43%) · acquire time 2ms→2000ms · 361 new "failed to acquire connection" errors · the deployment 4 minutes earlier that raised concurrency 8→64
⚠️ Contradicting evidence shown too: CPU stayed flat
🔧 Proposed fix: roll back — executed only after a second human approves. Every step audited.

What makes it different from "chat with your logs":

🧠 Deterministic first — detection, correlation, log clustering, trace analysis and scoring are tested code. The LLM (local, via Ollama — or none at all) only narrates and cites.
🔍 A verifier re-checks every AI claim against the evidence, deletes invented citations, and re-derives the confidence. Below 55% → routed to a human, not a playbook.
🔒 Local-first — nothing leaves your infrastructure. No API keys. $0 in API spend.
📊 Measured, not claimed — the repo ships a 119-scenario benchmark (14 failure modes + healthy controls):
 • 100% top-1 root-cause accuracy (first iteration: 96.5% — the fixes are public commits)
 • 100% detection · 0% false positives · 0% confidently-wrong
 • 0.39s median investigation time
 • Reproduce it yourself: `make eval`

And my favourite result is a failure: a small local model flipped a correct answer while "improving" it. The verifier's rank-stability guard caught it — and that negative result is published in the repo too. That's the whole philosophy: evidence over vibes.

Built with Python, FastAPI, PostgreSQL, Redis, OpenTelemetry, Prometheus, Grafana, Next.js, and Ollama — plus a seven-service demo shop with a 14-fault chaos engine you can break yourself.

🔗 Live demo: https://sentinel-phi-seven-74.vercel.app (login on the page — break something in the Chaos Lab, then ask the incident "Why?")
⭐ Source, docs, ADRs, threat model, benchmark: https://github.com/raunitgrey7/sentinel

If you run an SRE/platform team and want to try this on real telemetry (it ingests OpenTelemetry and Alertmanager directly), my DMs are open. Feedback, stars and brutal code review equally welcome. 🙏

#AIEngineering #SRE #DevOps #IncidentResponse #Observability #OpenTelemetry #LLM #OpenSource #Python #FastAPI #NextJS #TypeScript #PostgreSQL #Ollama #LocalLLM #PlatformEngineering #RootCauseAnalysis #AIOps #MachineLearning #SoftwareEngineering #BuildInPublic #DeveloperTools #Reliability #ChaosEngineering

---

## Shorter variant (if you prefer punchy)

Monitoring tells you WHAT broke. I built the thing that tells you WHY — with proof. 🛰️

Sentinel: open-source, local-first AI incident investigation.
→ Correlates logs, metrics, traces, deployments & git history into an evidence graph
→ Ranks root causes with an inspectable score; a verifier rejects any AI claim without evidence
→ Humans approve every action (four-eyes + audit log)
→ 119-case public benchmark: 100% top-1 accuracy, 0% false positives, 0.39s median
→ Runs on your infra. Local LLM via Ollama or no model at all. $0 API spend.

Live demo: https://sentinel-phi-seven-74.vercel.app · Code: https://github.com/raunitgrey7/sentinel

Break it yourself: inject a database-pool exhaustion in the Chaos Lab, watch it find the bad deployment, then ask it "Why not CPU saturation?" — it answers with citations and counter-evidence.

#SRE #AIEngineering #Observability #OpenSource #DevOps #IncidentResponse #LLM #Python #NextJS #BuildInPublic
