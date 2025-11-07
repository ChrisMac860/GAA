import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { isPlaceholderTeam, withinFixturesWindow, withinResultsWindow } from '../filters';
import { addDaysISO, todayISO } from '../dates';

describe('isPlaceholderTeam', () => {
  it('detects obvious placeholders', () => {
    expect(isPlaceholderTeam('Winner of Quarter Final 1')).toBe(true);
    expect(isPlaceholderTeam('Top Team Group 2')).toBe(true);
    expect(isPlaceholderTeam('Runner-up Group A')).toBe(true);
    expect(isPlaceholderTeam('TBC')).toBe(true);
    expect(isPlaceholderTeam('Unknown')).toBe(true);
  });

  it('detects slash pairings as placeholders', () => {
    expect(isPlaceholderTeam('Kilmeena/Caltra')).toBe(true);
  });

  it('does not flag real teams', () => {
    expect(isPlaceholderTeam('Kilmeena v Caltra')).toBe(false);
    expect(isPlaceholderTeam('Dublin')).toBe(false);
    expect(isPlaceholderTeam('Ciarraí')).toBe(false);
  });
});

describe('date windows', () => {
  const restoreEnv = { ...process.env };
  beforeEach(() => {
    process.env.NEXT_PUBLIC_RESULT_LOOKBACK_DAYS = '14';
    process.env.NEXT_PUBLIC_FIXTURE_LOOKAHEAD_DAYS = '14';
  });
  afterEach(() => {
    vi.useRealTimers();
    process.env = { ...restoreEnv };
  });

  it('results: includes [today-14, today], excludes outside', () => {
    // Pick a DST change day (last Sunday in March 2025 is 2025-03-30)
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2025-03-30T10:00:00Z'));
    const today = todayISO();
    const start = addDaysISO(today, -14);
    const before = addDaysISO(start, -1);
    const after = addDaysISO(today, 1);
    expect(withinResultsWindow(start)).toBe(true);
    expect(withinResultsWindow(today)).toBe(true);
    expect(withinResultsWindow(before)).toBe(false);
    expect(withinResultsWindow(after)).toBe(false);
  });

  it('fixtures: includes [today, today+14], excludes outside', () => {
    // Around autumn DST change (last Sunday in Oct 2025 is 2025-10-26)
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2025-10-26T10:00:00Z'));
    const today = todayISO();
    const end = addDaysISO(today, 14);
    const before = addDaysISO(today, -1);
    const after = addDaysISO(end, 1);
    expect(withinFixturesWindow(today)).toBe(true);
    expect(withinFixturesWindow(end)).toBe(true);
    expect(withinFixturesWindow(before)).toBe(false);
    expect(withinFixturesWindow(after)).toBe(false);
  });

  it('returns false for invalid dates', () => {
    expect(withinFixturesWindow('2025-13-40')).toBe(false);
    expect(withinResultsWindow('not-a-date')).toBe(false);
  });
});

