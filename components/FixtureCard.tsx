import { formatTimeLondon } from "@/lib/dates";
import { shortenCompetition } from "@/lib/competitions";
import type { Fixture } from "@/lib/data";

export default function FixtureCard({ fixture }: { fixture: Fixture }) {
  const { date, time, competition, home, away, venue, status, score } = fixture;
  return (
    <article className="panel p-4" aria-label={`${home} vs ${away}`}>
      <div className="flex items-center justify-between gap-2">
        <div className="text-sm" aria-label="Competition">
          {shortenCompetition(competition)}
        </div>
        <div className="text-sm font-bold" aria-label="Time">{formatTimeLondon(date, time)}</div>
      </div>
      <div className="mt-2 flex items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="truncate text-base font-extrabold">{home}</div>
          <div className="truncate text-base font-extrabold">{away}</div>
          <div className="mt-1 text-sm" aria-label="Venue">{venue}</div>
        </div>
        <div className="shrink-0 text-right">
          {status === "FT" ? (
            <div className="text-sm font-extrabold" aria-label="Full time score">
              {score}
            </div>
          ) : status === "PP" ? (
            <div className="text-sm font-extrabold" aria-label="Postponed">PP</div>
          ) : (
            <div className="text-sm" aria-label="Status">Scheduled</div>
          )}
        </div>
      </div>
    </article>
  );
}
