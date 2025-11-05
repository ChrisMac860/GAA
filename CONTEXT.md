# Project Context: GAA Fixtures & Results

This repository contains a fast, mobile‑first Next.js frontend (App Router, TypeScript, Tailwind) and a zero‑cost backend data pipeline that aggregates fixtures/results from open sources into static JSON consumable by the frontend. It is designed for Vercel deployment and GitHub Actions scheduling.

## Frontend (Next.js)
- Routes
  - `/` Landing with AnimatedTitle and “This Weekend’s Big Competitions”.
  - `/fixtures` Searchable (Irish↔English) upcoming fixtures, grouped by day.
  - `/results` Searchable (Irish↔English) recent results, grouped by day.
- UI/Perf
  - Minimal JS: server‑rendered lists, hydrated search only.
  - Skeleton shimmer while lists stream.
  - High‑contrast, large touch targets, sticky headers.
- Data
  - Reads `public/data/fixtures.json` and `public/data/results.json` with `cache: 'no-store'` so updates show immediately.

## Backend (Python 3.11 + Poetry)
- Commands
  - `python -m backend fetch`: run all enabled adapters and cache raw inputs to `backend/.cache`.
  - `python -m backend build`: normalise, merge, window and write JSON to `public/data`.
  - `python -m backend all`: fetch + build.
  - `python -m backend validate`: basic schema/field checks.
- Adapters (under `backend/adapters/`)
  - `gaa_gms.py` Foireann Open Data (preferred when configured).
  - `scraper_web.py` Province/WordPress scrapers (Ulster/Connacht/Munster themes), including results tab.
  - ClubZap/ICS scaffolds are present but disabled by default.
- Normalisation & Merge
  - Bilingual normalisation (Irish→English token map) builds a search index.
  - Dedupe prefers higher‑priority sources, more complete records (score/FT), and newest updates.
  - Competition popularity scoring for landing page.
- Windows/Output
  - Fixtures: default 14 days forward. A separate `scraper_days_forward` can widen future window for province pages (they often list 3–6 weeks ahead).
  - Results: default `results_days_back` (configurable). If none in window, a fallback selects latest FT items (default 365 days) to avoid an empty UI.
  - Output files: `public/data/fixtures.json`, `public/data/results.json`, `public/data/competitions.json`.

## Configuration (`backend/config.yaml`)
- Feature flags: enable/disable sources (`enable_gms`, `enable_scraper`, etc.).
- Source config: Foireann base path and params; province/county URLs for the scraper.
- Windows: `days_forward`, `days_back`, `scraper_days_forward`, `results_days_back`, `results_fallback_days`.
- Write policy: `preserve_on_empty` (set to `false` to always overwrite outputs).

## GitHub Actions
- Workflow at `.github/workflows/update-fixtures.yml` runs at 06:00/18:00 Europe/London and commits changed `public/data/*.json`.
- Provide secrets if enabling Open Data or ClubZap.

## How Data Flows End‑to‑End
1. Adapters fetch province/county pages (and/or APIs), with retries and user‑agent.
2. Parsers extract date, time, competition, teams, venue, and score.
   - Fixtures drop placeholder 00:00 times (per requirements).
   - Results keep FT rows even if time is missing/00:00 (normalised to 12:00) so results aren’t lost.
3. Scraper de‑duplicates items on (date, time, home, away, competition). Merge stage also dedupes across sources.
4. Records are normalised and windowed (fixtures/results).
5. Static JSON is written to `public/data/` for the Next.js app to serve.

## Extending Coverage
- Add county “fixtures/results” URLs under `scraper.urls` to improve recency (most activity is at county level).
- Enable GMS Open Data by configuring `gms.open_data` and feature flag.
- If specific sites use custom markup, add site‑specific parsers to `scraper_web.py`.

## Project Goals & Budgets
- Mobile‑first, sub‑second FCP; minimal hydration.
- HTML+CSS < 60kB, route JS < 50kB, JSON < 100kB.
- Accessible: semantic landmarks, focus rings, keyboardable controls.

## Quick Run
- Backend: `python -m backend all` (or with Poetry: `python -m poetry run python -m backend all`).
- Frontend: `npm run dev` and open `http://localhost:3000`.

## UI Notes
- Retro console aesthetic: blue background, white panels with black borders, bold black headings.
- Header strip and rectangular buttons keep contrast high.
- Footer includes a subtle support button (Buy Me A Coffee).
