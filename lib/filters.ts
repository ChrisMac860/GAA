import type { Fixture } from './data';
import { todayISO, addDaysISO, LONDON_TZ } from './dates';

// Read window sizes from env with defaults
export function getResultLookbackDays(): number {
  const v = parseInt(process.env.NEXT_PUBLIC_RESULT_LOOKBACK_DAYS ?? '', 10);
  return Number.isFinite(v) && v > 0 ? v : 14;
}

export function getFixtureLookaheadDays(): number {
  const v = parseInt(process.env.NEXT_PUBLIC_FIXTURE_LOOKAHEAD_DAYS ?? '', 10);
  return Number.isFinite(v) && v > 0 ? v : 14;
}

function stripDiacritics(s: string) {
  return s.normalize('NFD').replace(/[\u0300-\u036f]+/g, '');
}

export function isPlaceholderTeam(name: string): boolean {
  if (!name) return true;
  const raw = name.trim();
  const s = stripDiacritics(raw).toLowerCase();

  // Obvious placeholders
  if (/(^|\b)(tbd|tba|tbc|bye|unknown|to be (confirmed|decided))($|\b)/i.test(raw)) return true;

  // Winner/Loser/Runner-up patterns
  const phWords = [
    'winner', 'loser', 'runner-up', 'runner up', 'runners-up', 'runners up',
    'top team', 'first place', 'second place', 'third place', '4th place', '1st place', '2nd place', '3rd place'
  ];
  for (const w of phWords) if (s.includes(w)) return true;

  // Stage + number or group letters
  if (/(quarter\s*final|semi\s*final|final|prelim|preliminary|qualifier|play[- ]?off|round\s*\d+)/.test(s)) return true;
  if (/(group\s*[a-z]|group\s*\d+|pool\s*[a-z]|pool\s*\d+)/.test(s)) return true;

  // Shorthand stages like QF/SF/R1/R2
  if (/(^|\b)(qf|sf|rf|r\d{1,2})(\b|$)/.test(s)) return true;

  // Ambiguous placeholder like "Team A/Team B" often used before a prior tie is decided
  if (/^[^vvs]+\/.+$/i.test(raw) && !/\b(v|vs|versus)\b/i.test(raw)) return true;

  return false;
}

function isValidISODate(dateISO: string | undefined | null): dateISO is string {
  if (!dateISO) return false;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(dateISO)) return false;
  const [y, m, d] = dateISO.split('-').map((x) => parseInt(x, 10));
  const dt = new Date(Date.UTC(y, m - 1, d));
  return dt.getUTCFullYear() === y && dt.getUTCMonth() === m - 1 && dt.getUTCDate() === d;
}

export function withinResultsWindow(dateISO: string): boolean {
  if (!isValidISODate(dateISO)) return false;
  const today = todayISO(LONDON_TZ);
  const lookback = getResultLookbackDays();
  const start = addDaysISO(today, -lookback);
  return dateISO >= start && dateISO <= today;
}

export function withinFixturesWindow(dateISO: string): boolean {
  if (!isValidISODate(dateISO)) return false;
  const today = todayISO(LONDON_TZ);
  const ahead = getFixtureLookaheadDays();
  const end = addDaysISO(today, ahead);
  return dateISO >= today && dateISO <= end;
}

export function isRenderableFixture(f: Fixture): boolean {
  // Exclude placeholders and invalid dates early
  if (isPlaceholderTeam(f.home) || isPlaceholderTeam(f.away)) return false;
  return true;
}

export function filterUpcomingFixtures(fixtures: Fixture[]): Fixture[] {
  return fixtures.filter((f) => isRenderableFixture(f) && withinFixturesWindow(f.date) && f.status !== 'FT');
}

export function filterRecentResults(items: Fixture[]): Fixture[] {
  return items.filter((f) => isRenderableFixture(f) && withinResultsWindow(f.date));
}

