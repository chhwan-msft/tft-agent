# TFT Agent Repo

This repository contains two related projects for working with Teamfight Tactics (TFT) Set data and agent-powered tools:

- `src/tft-agents/` — a multi-agent project that helps users with TFT patch notes, explanations, and performance analysis. Agents are designed to answer user questions about patch changes and to assist with performance or strategy guidance.
- `src/tft-ingest/` — a data ingestion toolkit that fetches and normalizes TFT Set data (Units, Traits, Items) from CommunityDragon and community sources, enriches items with component recipes, and indexes the data into Azure AI Search using integrated vectorization. This module grounds the agents with up-to-date set knowledge.

## Structure

At a glance:

```
repo root
├─ pyproject.toml
├─ requirements.txt
├─ README.md  <- you are here
└─ src/
   ├─ tft-ingest/   <- ingestion tooling, see its README and .env.example
   └─ tft-agents/   <- multi-agent app, see its README or module docstrings
```

Important files and locations

- `src/tft-ingest/README.md` — detailed instructions for ingestion, index creation, and usage.
- `src/tft-ingest/.env.example` — example environment variables for Azure, CommunityDragon, and blob storage. Copy to `src/tft-ingest/.env` and fill in secrets.
- `src/tft-agents/` — contains `main.py`, `PatchNotesAgent.py`, and `TDTAgent.py` (agent entrypoints and logic).

## Quick start

1. Install dependencies (recommended in a virtualenv):

```bash
pip install -r requirements.txt
```

2. Review `src/tft-ingest/.env.example` and create `src/tft-ingest/.env` with your Azure and CDragon details if you plan to run ingestion.

3. See `src/tft-ingest/README.md` for ingestion steps; see `src/tft-agents/` for agent usage.

## Notes and next steps

- Keep secrets out of version control. Use `.env` locally and a secrets manager for deployments.
- If you want, I can:
  - Add a short example `.env` for `src/tft-agents` itself
  - Add top-level contribution/development notes or a quick test harness
