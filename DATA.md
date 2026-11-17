# Data

This file explains the project's **data sources** — where they come from, how to get them, and how to think about using them. It is the contextual companion to the [`data/`](data/) folder.

> **`DATA.md` is tracked in git. The `data/` folder is not.** Documentation about the data lives here, in version control, so the whole team shares one understanding. The datasets themselves live in `data/`, which is **git-ignored** — raw data is often large, private, or licensed, and must never be committed. Clone the repo, then populate `data/` locally by following the sources below.

## Where to look for sources

At the start of the project, before committing to a source, scan these in roughly this order:

1. **A source the club or a sponsor already provides.** If the project came with data, that's your primary source — document it first.
2. **Official / authoritative open data.** Government portals (e.g. data.gov), inter-governmental bodies, and official statistics agencies. Highest trust, usually well-documented, clear licensing.
3. **Curated dataset hubs.** Kaggle, Hugging Face Datasets, UCI ML Repository, Google Dataset Search, AWS/Azure open-data registries. Fast to start with; check the license and provenance.
4. **Domain-specific repositories / APIs.** Whatever is standard for the project's field (e.g. a scientific archive, a public API, a research consortium). Often the richest and most relevant.
5. **First-party collection.** Surveys, scraping (only where permitted), or instrumentation you build. Highest effort and the most responsibility — get PM sign-off first.

## How to think about using a source (high level)

Before you rely on a dataset, a member should be able to answer these — and record the answers in the source's row below:

- **License & permission.** Are we allowed to use it for this purpose, and to share results? If unclear, ask a PM before building on it.
- **Provenance.** Who produced it, when, and how? Freshness and collection method shape what conclusions are valid.
- **Fitness.** Does it actually measure what the project needs? Coverage, granularity, and sample size matter more than size.
- **Sensitivity.** Any PII, confidential, or ethically sensitive content? If yes, that dictates storage and handling — and it stays out of git regardless.
- **Reproducibility.** Can a teammate re-fetch it from your notes alone? If not, the source isn't documented well enough yet.

Choosing and vetting a source is a **judgment call** — surface it to a PM rather than deciding a major data direction alone.

## Source register

Document every source here as you adopt it. Replace these placeholders.

| Source | Origin / URL | Access method | License | Sensitivity | Notes |
|--------|--------------|---------------|---------|-------------|-------|
| Supplied IEEE × ADSC synthetic training trajectories | User-provided `IEEE_ADSC_Heat_Grid_Synthetic_Data.zip` | Manually unpack two CSVs into Git-ignored `model/data/` | TBD: redistribution terms not supplied | Synthetic; no reported personal data | 194,400 rows, 36 unmitigated RC scenarios; train/val/test 25/5/6. Local implementation requested by owner; confirm license before redistribution. |
| Supplied synthetic telemetry/control fixtures | Same user-provided package; `algorithm/fixtures/README_data_contract.md` | Existing `algorithm/fixtures/` CSVs; no network fetch | TBD: confirm redistribution permission | Synthetic; no reported personal data | 2,993 packets, three scripted commands/ACKs and rail configuration; not model accuracy ground truth. |
| Generated transformer comparison scenarios | Local `grid_model.physics_comparison` with explicit `model/configs/transformer.json` | Reproduce using `python -m grid_model compare-physics`; summaries/artifacts in ignored `model/reports/` | Project-generated inputs; Alliander dependency MPL-2.0 | Synthetic; no personal or utility data | User-requested architecture correction: 18 transformer scenarios, train/val/test 10/4/4. IEEE-generated and IEC-generated references are separate consistency experiments, NOT physical transformer ground truth or the original RC fixtures. |

## IEEE × ADSC local inputs

The project mandate additionally uses Git-ignored `model/data/` for supplied
inputs; preserve the root raw/interim/processed convention for future sources.
There is no automatic downloader because no public source URL or redistribution
license was supplied. Missing inputs produce explicit path errors. The original
CSVs are never replaced. The RC demo produces clearly labeled new virtual
measurements in Git-ignored `algorithm/runs/` and needs no training data.

Do not train against intervention-replay outcomes as if unmitigated. All values
are RC-emulated; probe temperatures are proxies and 70/80°C thresholds are demo
parameters. Physical data adoption requires separate source/license/sensitivity
review. Nothing under either data directory should be committed.

## Local layout convention

The `data/` folder is git-ignored, but keep a consistent structure inside it so everyone's local copy matches:

```
data/
├── raw/          # exactly as downloaded — never edit by hand
├── interim/      # partially processed, intermediate outputs
└── processed/    # analysis-ready, produced by the cleaning pipeline
```

Because `data/` isn't in git, the **pipeline that fetches and builds these folders** is what must be committed and reproducible — not the data itself.
