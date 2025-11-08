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
  const base = normalizeQuery(raw);
  const tokens = new Set(base.split(/\s+/).filter(Boolean));
  // Add synonyms so searches for 'senior' match 'sfc' and vice versa
  const has = (w: string) => tokens.has(w);
  if (has('senior')) tokens.add('sfc');
  if (has('intermediate')) tokens.add('ifc');
  if (has('junior')) tokens.add('jfc');
  if (has('sfc')) tokens.add('senior');
  if (has('ifc')) tokens.add('intermediate');
  if (has('jfc')) tokens.add('junior');
  return Array.from(tokens).join(' ');
}
