"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Fixture } from "@/lib/data";
import { formatTimeLondon } from "@/lib/dates";
import { normalizeQuery, buildIndexEntry } from "@/lib/search";
import { filterUpcomingFixtures } from "@/lib/filters";

export default function FixturesSearch({ fixtures, initialQuery }: { fixtures: Fixture[]; initialQuery: string }) {
  const [q, setQ] = useState(initialQuery ?? "");
  const [debounced, setDebounced] = useState(q);
  const timerRef = useRef<number | null>(null);

  // Keep URL in sync with query param without full reload
  useEffect(() => {
    if (timerRef.current) window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => setDebounced(q), 150);
    const url = new URL(window.location.href);
    if (q) url.searchParams.set("q", q); else url.searchParams.delete("q");
    window.history.replaceState({}, "", url.toString());
  }, [q]);

  // Filter out placeholders and out-of-window items before indexing/searching
  const filteredBase = useMemo(() => filterUpcomingFixtures(fixtures), [fixtures]);
  const index = useMemo(() => filteredBase.map((f) => ({ f, idx: buildIndexEntry(f) })), [filteredBase]);

  const filteredUpcoming = useMemo(() => {
    if (!debounced.trim()) return index.map((x) => x.f);
    const nq = normalizeQuery(debounced);
    const words = nq.split(/\s+/).filter(Boolean);
    return index
      .filter(({ idx }) => words.every((w) => idx.includes(w)))
      .map((x) => x.f);
  }, [index, debounced]);

  // Group by date ascending
  const grouped = useMemo(() => {
    const m = new Map<string, typeof filteredUpcoming>();
    for (const f of filteredUpcoming) {
      if (!m.has(f.date)) m.set(f.date, [] as unknown as typeof filteredUpcoming);
      (m.get(f.date) as Fixture[]).push(f);
    }
    return Array.from(m.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [filteredUpcoming]);

  return (
    <div className="space-y-3">
      <label className="sr-only" htmlFor="q">Search</label>
      <input
        id="q"
        type="search"
        inputMode="search"
        placeholder="Search (Irish or English)"
        className="w-full rounded-lg border border-gray-300 px-3 py-2"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />

      <p className="text-xs text-gray-600">The Irish search sort of works</p>
      <div className="max-h-[640px] overflow-y-auto panel">
        {grouped.length === 0 ? (
          <div className="p-4 text-sm text-gray-700">No matches. Try different keywords.</div>
        ) : (
          grouped.map(([date, items]) => (
            <div key={date} className="border-b last:border-b-0 border-gray-100">
              <div className="sticky top-0 z-10 bg-white/95 px-4 py-2 text-sm font-semibold text-gray-800">
                {date}
              </div>
              <ul className="grid gap-3 p-3" role="list" aria-label={date}>
                {items.map((f) => (
                  <li key={f.id} role="listitem">
                    <article className="rounded-2xl border border-gray-200 p-4 hover:shadow-sm">
                      <div className="flex items-center justify-between gap-2">
                        <div className="text-sm text-gray-600 truncate" title={f.competition}>{f.competition}</div>
                        <div className="text-sm font-medium text-gray-900">{formatTimeLondon(f.date, f.time)}</div>
                      </div>
                      <div className="mt-2 text-base font-semibold text-gray-900">
                        {f.home} <span className="text-gray-400">vs</span> {f.away}
                      </div>
                      {f.status !== "scheduled" && (
                        <div className="mt-1 text-sm text-gray-700">{f.status === "FT" ? f.score : f.status}</div>
                      )}
                    </article>
                  </li>
                ))}
              </ul>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
