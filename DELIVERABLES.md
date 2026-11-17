# Deliverables & Timeline

> **How to read this file.** This is the PMs' best current estimate of what the project needs to ship and roughly when. It is a **living plan, not a contract** — deliverables will be added, dropped, split, or resequenced as the team learns more. The authoritative, up-to-the-minute picture always lives in the repo's **GitHub Issues and Project board**; this file is the high-level narrative that keeps everyone oriented.
>
> The five software checkpoints follow `ENTROPY_AGENTS.md`, with simulation first.
> Physical commissioning is a separate approval-gated follow-up.

## Milestones at a glance

| # | Deliverable | Description | Owner (role) | Target |
|---|-------------|-------------|--------------|--------|
| 1 | Repository and interface | Packages, shared NDJSON schema and fixture validation so teams share one contract. | Both software teams | Checkpoint 1 |
| 2 | Deterministic closed loop | Mutable RC plant, fake bridge/controller, local interlocks, policy/ACK/retry; prioritized before ML to prove shedding and cooling. | Algorithm + embedded | Checkpoint 2 |
| 3 | Forecast comparisons | Persistence, RC, trained Ridge/LSTM/Transformer, causal splits, artifacts, held-out metrics and honest fallback. | Model team | Checkpoint 3 |
| 4 | Transport and firmware | Monitor-only USB serial, two dry-run ESP32 builds and compile/runtime output gates so software can progress before safe hardware configuration. | Algorithm + embedded | Checkpoint 4 |
| 5 | Dashboard and QA | Local dashboard, supervised virtual restore, SQLite/CSV, fault tests and reproducible handoff. | Both software teams | Checkpoint 5 |
| 6 | Physical commissioning | Boards/pins/calibration/polarity/ratings/thresholds, independent cutoff and supervised tests; separated because no hardware safety settings are approved. | Hardware lead + faculty | Pending approval |
| 7 | Transformer physics and detection correction | Implement source-verified IEEE C57.91-2011 and real Alliander IEC analysis; retain RC/Ridge rig benchmark, separate crossing/temperature metrics, independent rail profiles and model-domain gates to correct the original baseline-first architecture. | Both software teams | Software verification; physical validation pending |

## Timeline (rough)

```
Sequence: contract -> closed-loop demo -> model comparisons -> dry-run firmware
          -> dashboard and software QA
Later:    physical commissioning after human safety approval
Revision: source-verified oil physics + domain-separated comparisons/detection,
          independent rig profiles and software regression verification
```

## Working agreements

- **Each deliverable maps to one or more GitHub Issues.** The board is the source of truth; this file is the summary.
- **Dates are estimates.** When reality diverges, update the issue and, if the shift is material, this file. Don't let this file quietly go stale.
- **"Done" is defined per issue** via acceptance criteria — not by a date passing.
- **Reprioritize openly.** If a deliverable changes, a PM notes why in the issue so the decision is auditable.
