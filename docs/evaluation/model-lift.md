# Model lift study (local `qwen2.5:3b`, CPU-only)

Question: what does a small local model add to — or take away from — the deterministic
pipeline? Measured on three representative scenarios (pool exhaustion, cache outage,
deployment regression) on an i5-12500H laptop with 16 GB RAM, no GPU, with the Docker
stack running alongside. Full 119-case runs with a model are impractical on this hardware
(~4 min per investigation); the deterministic benchmark remains the reference.

| Run | Top-1 | Citation validity | Confidence (3 cases) | Investigation time |
|---|---|---|---|---|
| Deterministic narrator (reference) | 3/3 | 100% | 0.79 / 0.68 / 0.58 | 0.4 s |
| `qwen2.5:3b`, model may reorder freely (`ollama-smoke-before-guard.md`) | **2/3** | 100% | 0.40 / 0.41 / 0.67 | 248 s median |
| `qwen2.5:3b` + rank-stability guard (`ollama-smoke.md`) | 3/3 | 100% | 0.48 / 0.43 / 0.68 | 261 s median |

## What happened

1. **The narrator flipped a correct answer.** On the cache-outage case the model ranked
   *database query latency* above *cache unavailable* although the deterministic score gap
   was 0.25. Its citations for the promoted hypothesis were valid, so calibrated confidence
   did not catch it — only the overall low confidence (0.41 → human review) did.
2. **Fix: rank-stability guard** (`verifier._stabilize`). The narrator may reorder only
   within a deterministic score gap of 0.10; larger flips are rejected and recorded as a
   verifier issue the UI shows ("narrator preferred X but the deterministic score gap
   exceeds the reorder tolerance"). With the guard: 3/3.
3. **The model cross-examination is over-skeptical at 3B.** It "disagreed" with two correct
   root causes, citing evidence handles that in fact support them. Because model
   verification is only allowed to *lower* confidence, the effect is conservative:
   correct answers routed to human review rather than wrong answers reported confidently.
   That is the intended failure direction, at the cost of confidence.
4. **Citation validity was 100 %** in all runs — the model never invented a handle, and the
   verifier's handle check remained unexercised in practice here.
5. **Cost:** 150–340 s of model time per investigation on CPU, versus 0.4 s deterministic.

## Conclusions

* The deterministic pipeline is the product; the model is an optional narrator. The default
  provider stays `none`.
* A 3B model does not improve root-cause identification; it improves prose. Its verifier
  role should be treated as advisory at this size. Larger models (7B+ on a GPU) are the
  next experiment; the harness is ready (`SENTINEL_LLM_PROVIDER=ollama make eval`).
* Two guard rails were validated by this study: rank stability and one-directional
  confidence adjustment. Both exist because the model was wrong in a way the numbers
  caught.
