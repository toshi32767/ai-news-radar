# Investment Radar Migration Plan

This fork starts from `LearnPrompt/ai-news-radar` and keeps the upstream project
working while we validate whether the same pipeline can become an investment
research radar.

The first milestone is not to rewrite the site. It is to prove that the existing
static pipeline, JSON outputs, source health checks, story merging, and GitHub
Actions cadence can support investment-grade information workflows.

## Product Goal

Build an investment-layer radar that turns noisy public information into
auditable research leads:

- market and policy catalysts
- industry-chain events
- AI and technology catalysts
- company and disclosure events
- risk events
- evidence-ranked research clues

The output should be useful before it is decisive. News items are clues, not
trading signals. A story can enter strategy scoring only after it is linked to
stronger evidence such as official disclosures, policy documents, financial data,
price-volume behavior, order data, or other verifiable datasets.

## Source Strategy

Use three source layers.

### Layer 1: Stock Swarm Finance RSS

Keep the local `stock_swarm` RSS pipeline as the investment backbone:

- Jin10 and Jin10 important
- Eastmoney finance feeds
- Wallstreetcn live and hot feeds
- CLS important telegraph
- Sina finance China
- Caixin
- Yicai
- Xueqiu hot discussions
- State Council policy feeds
- PBOC feeds
- exchange notices

These sources are closer to macro, policy, liquidity, disclosure, and market
sentiment. They should remain the primary investment information stream.

### Layer 2: AI News Radar Cleaned Outputs

Consume the upstream cleaned outputs first:

- `data/latest-24h.json`
- `data/stories-merged.json`
- `data/source-status.json`

This is safer than directly copying every upstream source. The upstream project
already compresses thousands of raw items into AI-related records, adds source
tier metadata, and merges repeated events into stories.

### Layer 3: Selective Localized AI Sources

Only after validation, selectively add durable upstream sources into our own
source list:

- OpenAI News
- Google DeepMind
- Google AI Blog
- Hugging Face Blog
- GitHub AI and ML
- GitHub Changelog
- NVIDIA Generative AI Blog
- Microsoft AI Blog
- AI HOT or AIbase as Chinese AI vertical references

Avoid moving broad aggregators and social bridge sources into the default local
investment feed until their useful-signal rate is measured.

## Evidence Levels

Investment Radar should rank records by evidence strength.

- `L0 clue`: media item, social discussion, hot list, or external cleaned signal.
- `L1 source`: official source, policy document, exchange notice, company site,
  or primary-source article.
- `L2 data`: financial, market, volume, price, order, capacity, inventory,
  import-export, or other structured data.
- `L3 thesis`: a validated investment hypothesis with traceable evidence.

AI News Radar outputs usually enter as `L0 clue` or `L1 source`. Stock Swarm
market and Tushare-style data can raise a story to `L2`.

## Target Pipeline

The investment version should evolve toward this shape:

```text
ingest
  -> normalize
  -> source tiering
  -> domain relevance scoring
  -> dedupe
  -> story merge
  -> entity and industry-chain mapping
  -> evidence grading
  -> investment ranking
  -> static JSON and page output
```

## Initial Output Contract

Prototype outputs should live under `data/` or `output/` before the UI is
renamed:

- `investment-latest.json`
- `investment-stories.json`
- `investment-brief.json`
- `investment-risk-brief.json`
- `investment-stock-impacts.json`
- `investment-source-status.json`
- `investment-merge-log.json`

The first version can be JSON-only. The page should be adapted after the data
contract is stable.

## Migration Phases

### Phase 0: Fork Baseline

Keep upstream behavior intact.

- Fork and clone the upstream project.
- Keep `origin` pointing to our fork and `upstream` pointing to
  `LearnPrompt/ai-news-radar`.
- Run upstream tests and compile checks.
- Do not rename the UI or rewrite fetchers yet.

### Phase 1: External Investment Adapter

Add a small adapter that reads:

- Stock Swarm `daily_info_context_YYYYMMDD.json`
- Stock Swarm `daily_news_bundle.json`
- AI News Radar `latest-24h.json`
- AI News Radar `stories-merged.json`

Then write normalized prototype records for investment review.

### Phase 2: Domain Profiles

Replace the single AI relevance profile with investment domains:

- macro policy
- liquidity
- AI infrastructure
- semiconductor
- new energy
- robotics
- military
- medicine
- consumer
- risk

Each profile owns keywords, noise terms, entity aliases, source-tier weights,
time windows, and merge constraints.

### Phase 3: Story and Evidence Engine

Extend the upstream story merge into investment stories:

- merge repeated reports of the same event
- preserve all source references
- identify primary evidence
- attach evidence level
- attach industry-chain nodes
- attach validation requirements

### Phase 4: UI Adaptation

Only after the JSON is useful, adapt the static page:

- Today's Investment Brief
- Policy and Macro
- Industry Catalysts
- AI and Technology
- Company Events
- Risks
- Source Health
- Evidence Level
- Validation Needed

## Guardrails

- Do not let hot-list popularity become a trading signal.
- Do not promote `L0` clues into strategy inputs without stronger evidence.
- Keep private keys, OPML files, inbox contents, cookies, and paid API tokens out
  of the repository.
- Keep upstream sync simple until the investment data model has stabilized.
- Prefer additive files and adapters before invasive rewrites.

## First Feasibility Criteria

The fork is worth continuing if it can produce, for at least several runs:

- fresh JSON on schedule
- stable source health metadata
- less duplicate reading than the raw RSS stream
- at least 10 useful investment research clues per day
- visible separation between catalysts, background context, and risks
- traceable source links for every story
- no direct conversion from news into trade recommendations
