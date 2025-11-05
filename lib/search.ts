import type { Fixture } from "./data";
import { IRISH_TO_ENGLISH } from "./irish_map";

function stripDiacritics(s: string) {
  return s.normalize('NFD').replace(/[\u0300-\u036f]+/g, '');
}

export function normalizeQuery(s: string) {
  const lower = stripDiacritics(s.toLowerCase());
  const tokens = lower.replace(/[^a-z0-9\s-]/g, ' ').split(/\s+/).filter(Boolean);
  const mapped = tokens.map(t => IRISH_TO_ENGLISH[t] ?? t);
  return mapped.join(' ');
}

export function buildIndexEntry(f: Fixture) {
  const raw = `${f.home} ${f.away} ${f.competition} ${f.venue}`;
  return normalizeQuery(raw);
}
