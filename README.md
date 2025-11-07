# GAA Fixtures (Next.js)

Fast, mobile-first frontend for GAA fixtures and results. Built with Next.js (App Router), TypeScript, and Tailwind CSS — optimized for Vercel. No backend; reads static JSON from `public/data/fixtures.json`.

## Features
- Mobile-first, minimal JS, sub-second FCP target on 4G
- Pages: Landing (`/`), Fixtures (`/fixtures`)
- Reactbits-style animated hero title
- Skeleton loaders (shimmer) while lists stream in
- Server-rendered pages; client hydration only for search filtering
- Accessible landmarks, focus rings, sticky day headers

## Getting Started

### Install

Using pnpm (recommended):

```bash
pnpm i
```

Or npm:

```bash
npm i
```

### Develop

```bash
pnpm dev
```

Open http://localhost:3000

### Build

```bash
pnpm build && pnpm start
```

## Data

Fixtures are loaded from `public/data/fixtures.json` with this schema:

```json
[
  {
    "id": "IRL-2025-11-08-001",
    "date": "2025-11-08",
    "time": "13:30",
    "competition": "All-Ireland Senior Championship",
    "home": "Áth Cliath",
    "away": "Ciarraí",
    "venue": "Croke Park",
    "status": "scheduled",
    "score": "",
    "clubs": ["leinster/dublin","munster/kerry"]
  }
]
```

To update fixtures, replace `public/data/fixtures.json` with your data (keep under ~100 kB for performance).

Filtering & windows:
- Placeholder teams are hidden (e.g., “Winner of …”, “Runner-up Group A”, X/Y pairings before a prior tie is decided).
- Results show only last N days, fixtures only next M days. Tunable via env:
  - `NEXT_PUBLIC_RESULT_LOOKBACK_DAYS` (default 14)
  - `NEXT_PUBLIC_FIXTURE_LOOKAHEAD_DAYS` (default 14)

## Vercel Deploy

1. Push this repository to GitHub/GitLab/Bitbucket
2. Import the repo in Vercel
3. Deploy with defaults (no env vars needed)

The app fetches `/data/fixtures.json` from the public folder on the server, compatible with Edge.

## Testing

Run the Playwright smoke test:

```bash
pnpm exec playwright install --with-deps
pnpm dev &
pnpm test:e2e
```

The test ensures `/` loads and `/fixtures` renders a list.

## Routes
- `/` Landing with animated title and "This Weekend’s Big Competitions" (top 3)
- `/fixtures` Bilingual (Irish↔English) search, upcoming fixtures grouped by day (scrollable)
