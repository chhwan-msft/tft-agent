# TFT Agent Repo

This repository contains two related projects for working with Teamfight Tactics (TFT) Set data and agent-powered tools:

- `src/agents/` — a multi-agent project (plugins and agent wrappers) that helps users with TFT patch notes, explanations, and performance analysis.
- `src/data/ingestion` (also reachable under `src.data.ingestion`) — a data ingestion toolkit that fetches and normalizes TFT Set data (Units, Traits, Items) from CommunityDragon and community sources, enriches items with component recipes, and indexes the data into Azure AI Search using integrated vectorization. The indexed data is used to ground agents with up-to-date set knowledge.

## Structure

At a glance:

```
repo root
├─ pyproject.toml
├─ requirements.txt
├─ README.md  <- you are here
└─ src/
   ├─ data/   <- ingestion tooling, see its README and .env.example
   └─ agents/   <- multi-agent app, see its README or module docstrings
```

Important files and locations

- `src/data/README.md` — detailed instructions for ingestion, index creation, and usage.
- `src/.example.env` — example environment variables for Azure, CommunityDragon, and blob storage. Copy to `src/.env` and fill in secrets (the repo also contains `src/.example.env`).
- `src/agents/` — contains `main.py`, `PatchNotesAgent.py`, `TDTAgent.py`, and agent wrappers used by the orchestrator.

## Quick start

1. Install dependencies (recommended in a virtualenv):

```bash
uv pip install -r requirements.txt
```

2. Review `src/.example.env` and create `src/.env` with your Azure and CDragon details if you plan to run ingestion or agents.

3. See `src/data/README.md` for ingestion steps; see `src/agents/` for agent usage.

## Notes and next steps

- Keep secrets out of version control. Use `.env` locally and a secrets manager for deployments.
- If you want, I can:
  - Add a short example `.env` for `src/tft-agents` itself
  - Add top-level contribution/development notes or a quick test harness
