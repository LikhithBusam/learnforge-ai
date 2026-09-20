# Phase 7 — Growth Engine Evaluation Guide

## 1. Objective

Validate the mathematical correctness, trend stability, multi-window analysis, weakness detection, attention scoring, idempotency, isolation, and determinism of the Phase 7 Growth Engine.

---

## 2. Mandatory Evaluation Scenarios

### Scenario 1 — Strong Improvement
- **Input Sequence**: $0.20 \rightarrow 0.35 \rightarrow 0.55 \rightarrow 0.72$
- **Expected Trend**: `IMPROVING` ($\Delta = +0.52 > 0.05$).

### Scenario 2 — Decline
- **Input Sequence**: $0.85 \rightarrow 0.76 \rightarrow 0.64 \rightarrow 0.55$
- **Expected Trend**: `DECLINING` ($\Delta = -0.30 < -0.05$).

### Scenario 3 — Stable
- **Input Sequence**: $0.60 \rightarrow 0.61 \rightarrow 0.59 \rightarrow 0.60$
- **Expected Trend**: `STABLE` ($|\Delta| = 0.00 \le 0.05$).

### Scenario 4 — Insufficient Data
- **Input Sequence**: $[0.50]$ (1 observation)
- **Expected Trend**: `INSUFFICIENT_DATA`.

### Scenario 5 — Weak but Improving
- **Input Sequence**: $0.25 \rightarrow 0.32 \rightarrow 0.42$
- **Expected Trend**: `IMPROVING` ($\Delta = +0.17 > 0.05$).
- **Weakness Signal**: Weakness factor remains $> 0$ while trend correctly reflects growth.

### Scenario 6 — Strong but Declining
- **Input Sequence**: $0.88 \rightarrow 0.81 \rightarrow 0.72$
- **Expected Trend**: `DECLINING` ($\Delta = -0.16 < -0.05$).
- **Context**: Even with historically strong baseline, recent negative delta is captured.

### Scenario 7 — Confidence Sensitivity in Attention
- **Concept A**: Mastery = $0.35$, Confidence = $0.15 \implies$ Weakness factor $= (1 - 0.35) \times 0.15 = 0.0975$
- **Concept B**: Mastery = $0.35$, Confidence = $0.90 \implies$ Weakness factor $= (1 - 0.35) \times 0.90 = 0.5850$
- **Expected**: Concept B produces significantly higher attention score than Concept A.

### Scenario 8 — Recent Failure Burst
- Strong mastery baseline with a burst of recent incorrect attempts.
- **Expected**: Mistake factor scales up attention score and marks `attention_required = True`.

### Scenario 9 — Inactivity Signal
- Activity telemetry status: `ACTIVITY SIGNAL DEFERRED`.
- **Expected**: Inactivity factor contributes $0.0$ default weight without fabricating synthetic data.

### Scenario 10 — Determinism
- Two independent evaluation runs across a multi-step sequence produce bitwise identical DTOs and floats.
