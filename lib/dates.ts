export const LONDON_TZ = "Europe/London" as const;

function parts(date = new Date(), timeZone = LONDON_TZ) {
  const p = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);
  const y = p.find((x) => x.type === "year")!.value;
  const m = p.find((x) => x.type === "month")!.value;
  const d = p.find((x) => x.type === "day")!.value;
  return { y, m, d };
}

export function todayISO(timeZone = LONDON_TZ) {
  const { y, m, d } = parts(new Date(), timeZone);
  return `${y}-${m}-${d}`;
}

export function tomorrowISO(timeZone = LONDON_TZ) {
  const now = new Date();
  const tmr = new Date(now.getTime() + 24 * 60 * 60 * 1000);
  const { y, m, d } = parts(tmr, timeZone);
  return `${y}-${m}-${d}`;
}

export function formatTimeLondon(dateISO: string, hhmm: string) {
  const [y, m, d] = dateISO.split("-").map((s) => parseInt(s, 10));
  const [hh, mm] = hhmm.split(":" ).map((s) => parseInt(s, 10));
  const utc = new Date(Date.UTC(y, m - 1, d, hh, mm, 0));
  return new Intl.DateTimeFormat("en-GB", { timeStyle: "short", timeZone: LONDON_TZ }).format(utc);
}

const WEEKDAY_MAP: Record<string, number> = {
  Sunday: 0,
  Monday: 1,
  Tuesday: 2,
  Wednesday: 3,
  Thursday: 4,
  Friday: 5,
  Saturday: 6
};

export function nextWeekendLondon() {
  const now = new Date();
  const weekdayStr = new Intl.DateTimeFormat('en-GB', { weekday: 'long', timeZone: LONDON_TZ }).format(now);
  const dow = WEEKDAY_MAP[weekdayStr];
  const daysToSaturday = (6 - dow + 7) % 7; // if Sat => 0
  // Build Saturday and Sunday ISO strings
  const nowParts = new Intl.DateTimeFormat('en-CA', { timeZone: LONDON_TZ, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(now);
  const y = parseInt(nowParts.find(p => p.type === 'year')!.value, 10);
  const m = parseInt(nowParts.find(p => p.type === 'month')!.value, 10);
  const d = parseInt(nowParts.find(p => p.type === 'day')!.value, 10);
  const base = new Date(Date.UTC(y, m - 1, d));
  const sat = new Date(base.getTime() + daysToSaturday * 86400000);
  const sun = new Date(sat.getTime() + 86400000);
  const satParts = new Intl.DateTimeFormat('en-CA', { timeZone: LONDON_TZ, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(sat);
  const sunParts = new Intl.DateTimeFormat('en-CA', { timeZone: LONDON_TZ, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(sun);
  const saturdayISO = `${satParts.find(p=>p.type==='year')!.value}-${satParts.find(p=>p.type==='month')!.value}-${satParts.find(p=>p.type==='day')!.value}`;
  const sundayISO = `${sunParts.find(p=>p.type==='year')!.value}-${sunParts.find(p=>p.type==='month')!.value}-${sunParts.find(p=>p.type==='day')!.value}`;
  return { saturdayISO, sundayISO };
}

export function prevWeekendLondon() {
  const now = new Date();
  const weekdayStr = new Intl.DateTimeFormat('en-GB', { weekday: 'long', timeZone: LONDON_TZ }).format(now);
  const dow = WEEKDAY_MAP[weekdayStr]; // Sun=0..Sat=6
  const nowParts = new Intl.DateTimeFormat('en-CA', { timeZone: LONDON_TZ, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(now);
  const y = parseInt(nowParts.find(p => p.type === 'year')!.value, 10);
  const m = parseInt(nowParts.find(p => p.type === 'month')!.value, 10);
  const d = parseInt(nowParts.find(p => p.type === 'day')!.value, 10);
  const base = new Date(Date.UTC(y, m - 1, d));
  const daysSinceSaturday = (dow - 6 + 7) % 7; // Sun=>1, Mon=>2,... Sat=>0
  const lastSat = new Date(base.getTime() - daysSinceSaturday * 86400000);
  const lastSun = new Date(lastSat.getTime() + 86400000);
  const satParts = new Intl.DateTimeFormat('en-CA', { timeZone: LONDON_TZ, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(lastSat);
  const sunParts = new Intl.DateTimeFormat('en-CA', { timeZone: LONDON_TZ, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(lastSun);
  const saturdayISO = `${satParts.find(p=>p.type==='year')!.value}-${satParts.find(p=>p.type==='month')!.value}-${satParts.find(p=>p.type==='day')!.value}`;
  const sundayISO = `${sunParts.find(p=>p.type==='year')!.value}-${sunParts.find(p=>p.type==='month')!.value}-${sunParts.find(p=>p.type==='day')!.value}`;
  return { saturdayISO, sundayISO };
}

export function timeToMinutes(hhmm: string) {
  const [h, m] = hhmm.split(":").map((x) => parseInt(x, 10));
  if (Number.isNaN(h) || Number.isNaN(m)) return 0;
  return h * 60 + m;
}

export function isBetweenNoonAndFive(hhmm: string) {
  const mins = timeToMinutes(hhmm);
  return mins >= 12 * 60 && mins <= 17 * 60; // inclusive 12:00–17:00
}

export function addDaysISO(dateISO: string, days: number) {
  const [y, m, d] = dateISO.split('-').map((s) => parseInt(s, 10));
  const dt = new Date(Date.UTC(y, m - 1, d));
  dt.setUTCDate(dt.getUTCDate() + days);
  const yy = dt.getUTCFullYear();
  const mm = String(dt.getUTCMonth() + 1).padStart(2, '0');
  const dd = String(dt.getUTCDate()).padStart(2, '0');
  return `${yy}-${mm}-${dd}`;
}
