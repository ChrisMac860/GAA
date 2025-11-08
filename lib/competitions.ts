// Utilities to standardise competition display labels

function stripDiacritics(s: string) {
  return s.normalize('NFD').replace(/[\u0300-\u036f]+/g, '');
}

function findProvince(s: string): string | null {
  const m = stripDiacritics(s).toLowerCase().match(/\b(ulster|leinster|munster|connacht)\b/);
  if (!m) return null;
  const word = m[1];
  return word.charAt(0).toUpperCase() + word.slice(1);
}

function findStage(s: string): string | null {
  const lower = stripDiacritics(s).toLowerCase();
  const stageRe = /(quarter\s*final|semi\s*final|final|round\s*\d+)/i;
  const m = lower.match(stageRe);
  if (!m) return null;
  // Return the substring from the original with similar casing when possible
  const idx = lower.indexOf(m[1]);
  if (idx >= 0) {
    return s.substring(idx, idx + m[1].length);
  }
  return m[1];
}

function levelAbbr(s: string): 'SFC' | 'IFC' | 'JFC' | null {
  const lower = stripDiacritics(s).toLowerCase();
  if (/(^|\b)senior(\b|$)/.test(lower)) return 'SFC';
  if (/(^|\b)intermediate(\b|$)/.test(lower)) return 'IFC';
  if (/(^|\b)junior(\b|$)/.test(lower)) return 'JFC';
  // Sometimes the level is already abbreviated
  if (/(^|\b)sfc(\b|$)/.test(lower)) return 'SFC';
  if (/(^|\b)ifc(\b|$)/.test(lower)) return 'IFC';
  if (/(^|\b)jfc(\b|$)/.test(lower)) return 'JFC';
  return null;
}

export function shortenCompetition(original: string): string {
  const abbr = levelAbbr(original);
  if (!abbr) return original; // Not a recognised football championship level
  const prov = findProvince(original);
  const stage = findStage(original);
  const parts: string[] = [];
  if (prov) parts.push(prov);
  parts.push(abbr);
  if (stage) parts.push(stage.replace(/\s+/g, ' '));
  return parts.join(' ');
}

export function competitionLevelAbbr(competition: string): 'SFC' | 'IFC' | 'JFC' | null {
  return levelAbbr(competition);
}

