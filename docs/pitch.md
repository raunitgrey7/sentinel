# Sentinel — the complete pitch

*How to pitch Sentinel to investors and engineering leaders: what to say, in what order,
with every number you can defend and where it comes from. Slides: `docs/pitch/Sentinel-Pitch.pptx`.
Live demo: dashboard on Vercel, backend on Hugging Face Spaces (links in the README).*

---

## 0. The one-liner

> **Monitoring tells you a service is unhealthy. Sentinel tells you why — and proves it.**

If you get one sentence, use that. If you get two:

> Sentinel turns logs, metrics, traces, deployments and Git history into an evidence
> graph, ranks root-cause hypotheses with an inspectable score, and verifies every AI
> claim against the evidence before reporting a confidence. Humans approve every action.

---

## 1. The 3-minute verbal pitch (say this)

**[Problem — 40 seconds]**
"At 2:13 PM the payment service starts throwing errors. Latency climbs, database
connections climb, checkouts fail. Every dashboard lights up — the gateway, the order
service, the frontend, all red. Every tool you own says *something is wrong*. Not one of
them says *what changed and why*. So five engineers join a call, open thirty tabs, and
spend the next hour doing manual correlation — and most of that hour is diagnosis, not
fixing. The industry's answer has been to bolt a chatbot onto the logs. That gives you a
confident paragraph with no evidence, no reproducibility, and a prompt-injection surface
the size of your log volume."

**[What we built — 60 seconds]**
"Sentinel is a self-hosted incident investigation platform. It ingests the telemetry you
already have — OpenTelemetry-shaped logs, metrics, traces, plus deployments and commits —
detects incidents deterministically, and then runs seven specialised investigators:
metrics deviations against baselines, log template clustering, trace critical paths,
deployment proximity, dependency blast radius, and retrieval over your past incidents.
Everything lands in an evidence graph with citation handles the system itself minted.
A catalog of failure modes turns those signals into ranked hypotheses with an explicit,
inspectable score. Only then does a local language model get involved — it narrates and
cites. And here's the part nobody else does: a verifier re-checks the model's claims
against the evidence, throws out invalid citations, surfaces the contradictions it
ignored, and re-derives the confidence. If confidence is low, the incident routes to a
human, not a playbook. Nothing executes without a second person approving it, and every
step is audited."

**[Proof — 40 seconds]**
"We don't claim accuracy, we measure it. The repo ships a benchmark: 119 synthetic
production failures across 14 root-cause categories, with healthy controls, noise and
deliberately confounding deployments. Ground truth never reaches the pipeline. Latest
run: 100% top-1 root-cause accuracy, 100% detection, zero false positives on healthy
systems, zero confidently-wrong answers, median investigation time 0.39 seconds — and
that's with **no model at all**, because the deterministic engine is the product. The
first iteration scored 96.5%; the diff that fixed it is in the repo. When we did wire in
a small local model, it flipped a correct answer — our verifier caught the pattern, we
added a rank-stability guard, and we published that negative result too. That's the
culture this system is built on."

**[Why it wins — 30 seconds]**
"Three structural advantages. One: local-first — incident data is the most sensitive data
a company has, and with Sentinel nothing leaves the building; the model is Ollama on
localhost or nothing. Two: it sits beside existing monitoring, not instead of it —
ingestion is OpenTelemetry-aligned and it accepts Alertmanager webhooks directly. Three:
it's measurable — every claim in this pitch is a number in the repo you can regenerate
with one command."

**[Ask — 10 seconds]**
"It's open source, it's deployed, and you can break it yourself in the chaos lab right
now. I'm looking for design partners with real telemetry — and for [the role / the
investment] to take it there."

---

## 2. The 30-second elevator version

"Every company has monitoring that says *payment-service is unhealthy*. Nobody has a
system that says *why* and can prove it. Sentinel investigates incidents the way a good
SRE does — metrics, logs, traces, deployments, history — builds an evidence graph, ranks
root causes with a score you can inspect, and verifies every AI claim before reporting
confidence. It runs entirely on your infrastructure, needs no API keys, and ships with a
119-case benchmark where it currently identifies the right root cause 100% of the time
with zero false positives. The AI is the least interesting part — the verification
architecture is the product."

---

## 3. Every statistic you can say, and its source

Say only these numbers. Each one is regenerable from the repository.

| Number | Say it as | Source |
|---|---|---|
| **100% / 100%** | top-1 / top-3 root-cause accuracy, latest benchmark | `docs/evaluation/latest.md` (`make eval`) |
| **96.5% → 100%** | first iteration → current; "the fixes are two commits you can read" | `docs/evaluation/full-run1.md` |
| **119 cases** | 113 faults across **14 root-cause categories** + 6 healthy controls | `docs/evaluation/methodology.md` |
| **100%** | detection rate | latest.md |
| **100%** | evidence precision — cited evidence is relevant to the *true* cause | latest.md |
| **100%** | citation validity — every claim backed by real, system-minted evidence | latest.md |
| **0%** | false positives on healthy controls | latest.md |
| **0%** | confidently-wrong rate (wrong answer with confidence ≥ 0.55) | latest.md |
| **0.39 s / 0.63 s** | median / p95 end-to-end investigation time | latest.md |
| **0.32 ECE** | calibration error — *in the safe direction*: the system under-claims | latest.md + `docs/evaluation/model-lift.md` |
| **~161 s** | mean onset → alert-condition gap in the benchmark (rule `for` windows dominate) | latest.md |
| **2/3 → 3/3** | small-model study: free reordering flipped a correct answer; the rank-stability guard fixed it | `docs/evaluation/model-lift.md` |
| **7 investigators, 11 stages, 13 failure modes** | the deterministic engine | `docs/architecture/investigation-pipeline.md` |
| **69 tests** | unit + integration + chaos, plus a CI quality gate (accuracy ≥ 85%, FP ≤ 10%, citations ≥ 95%) | `.github/workflows/ci.yml` |
| **₹0 / $0** | API spend — local models via Ollama, or no model at all | ADR-0003 |
| **1 command** | `make eval` reproduces every number above | Makefile |

**Numbers to avoid claiming as your own:** industry MTTR/downtime-cost figures. If asked,
say "downtime cost estimates vary wildly by industry — what's constant is that most of
MTTR is diagnosis, and that's the part we compress." Never present the benchmark as real-world
accuracy — see the honesty section below; it's what makes the rest credible.

**The honesty preamble (use it, it disarms diligence):**
"Two caveats before you ask. The telemetry is synthetic, and the failure catalog and
scenarios share an author — the methodology doc lists this under threats to validity.
That's why the number that matters isn't 100%, it's the *machinery*: ground-truth
benchmark, healthy controls, confounders, a confusion matrix, a published miss, and a CI
gate that fails the build if accuracy regresses. Design partners on real telemetry are
exactly the next step."

---

## 4. "How is it better?" — the comparison you can defend

| | Observability suites (Datadog/NR/Dynatrace class) | Incident tools (PagerDuty/incident.io class) | "AI SRE" chatbots | **Sentinel** |
|---|---|---|---|---|
| Detects | ✓ alerts | pages people | — | ✓ deterministic rules + Alertmanager intake |
| Explains **why** | anomaly widgets | — | unsupported prose | ranked hypotheses with cited evidence |
| Shows contradictions | — | — | — | ✓ first-class, on the root-cause card |
| Confidence | — | — | theatrical | re-derived from evidence; capped; low → human review |
| Data locality | mostly SaaS | n/a | mostly SaaS | ✓ self-hosted, local model or none |
| Acts | — | runbooks | sometimes, unsafely | proposed → four-eyes approval → verified, audited |
| Measured accuracy | — | — | — | ✓ public, regenerable benchmark |
| Injection surface | n/a | n/a | the whole log stream | telemetry treated as data; verifier rejects fabrications |

Positioning sentence: **"We're not replacing your monitoring — we're the investigation
layer on top of it."** That kills the "Datadog will crush you" objection: Sentinel reads
the same OTel/Prometheus exhaust and is bought by teams who can't ship telemetry to a
third-party AI anyway.

## 5. Objection handling

* **"Isn't this just RAG over logs?"** — No. Retrieval is one of seven investigators and
  contributes at most a 0.25-weighted signal. The ranking comes from a deterministic
  catalog + scorer; the benchmark runs at 100% with retrieval *and* the model disabled.
* **"LLMs hallucinate."** — Ours can't hallucinate *evidence*: it can only cite handles the
  system minted, the verifier deletes anything else, and in our study citation validity
  was 100%. When the model was actively wrong (it reordered a correct answer away), the
  guard caught it — and we published that.
* **"Why will you beat Datadog Watchdog?"** — Different buyer constraint: our wedge is
  *data can't leave* + *show me the evidence*. Also: they can't publish a benchmark like
  this without inviting comparison; an open-source project grows on exactly that.
* **"What breaks at scale?"** — Telemetry write volume (path: partitioning/ClickHouse
  behind the same store interface), retrieval (pgvector, ADR-0004), hand-tuned catalog
  weights (path: learned scoring once labelled real incidents exist). All written down.
* **"Where's the moat?"** — The failure-mode catalog + verification corpus compounds with
  every design partner; the benchmark becomes the category's yardstick; local-first is a
  structural position SaaS incumbents can't easily follow.

---

## 6. Targeted clients & companies

**Ideal customer profile (ICP):** 30–500 engineers, 10–200 services, an on-call rotation
that hurts, telemetry already flowing (OTel/Prometheus/ELK), and at least one reason data
cannot go to a third-party AI (regulation, contracts, or sovereignty).

**Segment A — regulated & data-sensitive (the wedge, sell first):**
fintech/payments (Razorpay, PhonePe, Paytm, Juspay, Stripe-class processors, NPCI
ecosystem partners), banking/insurance platform teams (HDFC, ICICI, Bajaj Finserv tech
arms), health-tech (Practo, PharmEasy, Innovaccer), defence/gov-adjacent SaaS. *Pitch
angle: "AI incident analysis your compliance team will actually approve — nothing leaves
your VPC."*

**Segment B — scaled consumer platforms with brutal on-call:**
e-commerce & delivery (Flipkart, Meesho, Zomato, Swiggy, Zepto, BigBasket), mobility
(Ola, Uber-scale regional players), travel (MakeMyTrip, Ixigo), gaming/streaming (Dream11,
Hotstar-class). *Pitch angle: "one incident, not three; minutes of diagnosis, not hours —
during your peak-sale war rooms."*

**Segment C — mid-market SaaS & platform-engineering teams globally:**
companies (Postman, Browserstack, Freshworks, Zoho-scale and smaller) standardising on
OpenTelemetry with 2–10-person platform teams who own reliability but can't afford a
Datadog-everything bill. *Pitch angle: "open-source core, runs beside what you have,
measurable before you pay anything."*

**Segment D — MSPs / SRE consultancies & hosting providers:**
firms operating reliability for many clients (One2N-style SRE consultancies, managed
Kubernetes providers, regional clouds like E2E Networks). *Pitch angle: multi-tenant
control plane roadmap; they become distribution.*

**Who not to chase yet:** 5-person startups (no incident volume), and Fortune-100 with
entrenched Dynatrace contracts (18-month cycles). Land mid-market, expand up.

**First-10-conversations list (practical):** engineering leaders you can reach at
Segment A/B companies above + open-source channels: CNCF/OpenTelemetry community, SRE
India / SREcon, r/sre, Hacker News "Show HN", Kubernetes Slack #observability. The
GitHub repo *is* the top of funnel; the benchmark is the demo hook.

**Investor targeting:** seed funds with dev-tools/infra theses and open-source
portfolios — in India: Accel India, Peak XV Surge, Blume, Together Fund, Neon; global
OSS-friendly: OSS Capital, Essence VC, Heavybit, boldstart, Uncorrelated. Angels who
built devtools/observability companies. Lead with the benchmark culture — that's what
differentiates a "GPT wrapper" pitch from an infrastructure pitch.

---

## 7. The live demo script (5 minutes, do this while talking)

1. Open the dashboard (Vercel) → Overview: 12 services, healthy.
2. Chaos Lab → `payment-service` / `db_pool_exhaustion` → **Inject**. "We're breaking
   production on purpose. Sentinel is not told what we injected."
3. Overview: watch payment go red, then order-service, gateway, frontend. "Cascade."
4. Incidents: **one** incident, primary re-pointed to payment-service. "Symptoms merged,
   suspect identified by walking the dependency graph."
5. Incident page: root-cause card — *Database connection-pool exhaustion*, ~87%, with the
   contradiction ("CPU stayed flat") visible. "Calibrated, not theatrical."
6. Why? tab: ask "Why not CPU saturation?" → cited answer with counter-evidence.
7. Evidence graph tab. "This is what the verifier walks."
8. Remediation: request → approve (four-eyes) → execute rollback → verified + audit.
9. Evaluation page: the 119-case table. "You don't have to believe me — run `make eval`."

Fallback if the model/backend is cold: everything still works — the deterministic
narrator takes over and the UI says so. That *is* the pitch.

---

## 8. Business model (when asked)

Open-source core (Apache-2.0) → paid: enterprise adapters (Kubernetes/Argo/feature-flag
execution), SSO/OIDC + compliance pack, multi-tenant control plane, supported builds, and
eventually a managed control plane with the data plane staying on-prem. Standard
open-core motion: the free tier is the whole investigation engine — adoption first,
monetise operations at scale.

## 9. Close

"Reality → evidence → hypotheses → verification → human decision. That architecture is
the product. The LLM is the least interesting part — and that's exactly why this works."
