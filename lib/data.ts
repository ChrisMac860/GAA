import 'server-only';
import { headers } from 'next/headers';

export type FixtureStatus = 'scheduled' | 'FT' | 'PP';

export type Fixture = {
  id: string;
  date: string; // YYYY-MM-DD
  time: string; // HH:mm (local)
  competition: string;
  home: string;
  away: string;
  venue: string;
  status: FixtureStatus;
  score: string;
  clubs: string[]; // slugs
};

async function getBaseUrl() {
  const h = await headers();
  const proto = h.get('x-forwarded-proto') ?? 'http';
  const host = h.get('x-forwarded-host') ?? h.get('host');
  if (!host) return 'http://localhost:3000';
  return `${proto}://${host}`;
}

export async function loadFixtures(): Promise<Fixture[]> {
  const base = await getBaseUrl();
  const res = await fetch(`${base}/data/fixtures.json`, {
    cache: 'no-store'
  });
  if (!res.ok) {
    throw new Error(`Failed to load fixtures: ${res.status}`);
  }
  const data = (await res.json()) as Fixture[];
  return data;
}

export function distinctClubs(fixtures: Fixture[]) {
  const map = new Map<string, string>();
  for (const f of fixtures) {
    const [homeSlug, awaySlug] = f.clubs;
    map.set(homeSlug, f.home);
    map.set(awaySlug, f.away);
  }
  return Array.from(map.entries()).map(([slug, name]) => ({ slug, name })).sort((a, b) => a.name.localeCompare(b.name));
}

export async function loadResults(): Promise<Fixture[]> {
  const base = await getBaseUrl();
  const res = await fetch(`${base}/data/results.json`, {
    cache: 'no-store'
  });
  if (!res.ok) {
    throw new Error(`Failed to load results: ${res.status}`);
  }
  const data = (await res.json()) as Fixture[];
  return data;
}
