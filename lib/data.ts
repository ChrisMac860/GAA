import 'server-only';
import { headers } from 'next/headers';
import { unstable_noStore as noStore } from 'next/cache';
import fs from 'node:fs/promises';
import path from 'node:path';

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

async function readPublicJson<T>(filename: string): Promise<T> {
  const filePath = path.join(process.cwd(), 'public', 'data', filename);
  const raw = await fs.readFile(filePath, 'utf8');
  return JSON.parse(raw) as T;
}

export async function loadFixtures(): Promise<Fixture[]> {
  noStore();
  try {
    return await readPublicJson<Fixture[]>('fixtures.json');
  } catch (e) {
    try {
      const mod = await import('@/public/data/fixtures.json');
      // Cast through unknown to avoid strict structural typing on JSON modules
      return (mod as unknown as { default: Fixture[] }).default;
    } catch {}
    const base = await getBaseUrl();
    const res = await fetch(`${base}/data/fixtures.json`, { cache: 'no-store' });
    if (!res.ok) throw new Error(`Failed to load fixtures: ${res.status}`);
    return (await res.json()) as Fixture[];
  }
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
  noStore();
  try {
    return await readPublicJson<Fixture[]>('results.json');
  } catch (e) {
    try {
      const mod = await import('@/public/data/results.json');
      return (mod as unknown as { default: Fixture[] }).default;
    } catch {}
    const base = await getBaseUrl();
    const res = await fetch(`${base}/data/results.json`, { cache: 'no-store' });
    if (!res.ok) throw new Error(`Failed to load results: ${res.status}`);
    return (await res.json()) as Fixture[];
  }
}
