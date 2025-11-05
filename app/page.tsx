import { Suspense } from "react";
import AnimatedTitle from "@/components/AnimatedTitle";
import SkeletonList from "@/components/SkeletonList";
import { loadFixtures, type Fixture, loadResults } from "@/lib/data";
import { nextWeekendLondon, prevWeekendLondon, isBetweenNoonAndFive, addDaysISO } from "@/lib/dates";
import FixtureCard from "@/components/FixtureCard";

export const metadata = {
  title: "GAA Fixtures & Results",
  description: "Fast, mobile-first GAA fixtures."
};

export const dynamic = "force-dynamic";

function shuffle<T>(arr: T[]): T[] { const a = [...arr]; for (let i=a.length-1;i>0;i--) { const j = Math.floor(Math.random()*(i+1)); [a[i],a[j]]=[a[j],a[i]]; } return a; }

async function WeekendPicks() {
  await new Promise((r) => setTimeout(r, 320));
  const fixtures = await loadFixtures();
  const { saturdayISO, sundayISO } = nextWeekendLondon();
  const fridayISO = addDaysISO(saturdayISO, -1);
  const inRange = (d: string) => d >= fridayISO && d <= sundayISO;
  const prime = fixtures.filter(f => inRange(f.date) && isBetweenNoonAndFive(f.time));
  const others = fixtures.filter(f => inRange(f.date) && !isBetweenNoonAndFive(f.time));
  const picks: Fixture[] = [];
  picks.push(...shuffle(prime).slice(0, 4));
  if (picks.length < 4) {
    const remaining = shuffle(others).filter(x => !picks.find(p => p.id === x.id));
    picks.push(...remaining.slice(0, 4 - picks.length));
  }
  // If still short, fill from anywhere in fixtures (random), avoiding duplicates
  if (picks.length < 4) {
    const anywhere = shuffle(fixtures).filter(x => !picks.find(p => p.id === x.id));
    picks.push(...anywhere.slice(0, 4 - picks.length));
  }
  if (picks.length === 0) return <p className="text-gray-700">No fixtures this weekend.</p>;
  return <div className="grid gap-3" role="list" aria-label="This Weekend’s Picks">{picks.map(f => <FixtureCard key={f.id} fixture={f} />)}</div>;
}

async function PreviousWeekendPicks() {
  await new Promise((r) => setTimeout(r, 320));
  const results = await loadResults();
  const { saturdayISO, sundayISO } = prevWeekendLondon();
  const fridayISO = addDaysISO(saturdayISO, -1);
  const inRange = (d: string) => d >= fridayISO && d <= sundayISO;
  const inWeekend = results.filter(f => f.status === 'FT' && inRange(f.date));
  const prime = inWeekend.filter(f => isBetweenNoonAndFive(f.time));
  const others = inWeekend.filter(f => !isBetweenNoonAndFive(f.time));
  const picks: Fixture[] = [];
  picks.push(...shuffle(prime).slice(0, 4));
  if (picks.length < 4) {
    const remaining = shuffle(others).filter(x => !picks.find(p => p.id === x.id));
    picks.push(...remaining.slice(0, 4 - picks.length));
  }
  // If still short, fill from any FT result
  if (picks.length < 4) {
    const anywhere = shuffle(results.filter(f => f.status === 'FT')).filter(x => !picks.find(p => p.id === x.id));
    picks.push(...anywhere.slice(0, 4 - picks.length));
  }
  if (picks.length === 0) return <p className="text-gray-700">No highlights from last weekend.</p>;
  return <div className="grid gap-3" role="list" aria-label="Last Weekend’s Highlights">{picks.map(f => <FixtureCard key={f.id} fixture={f} />)}</div>;
}

export default function Page() {
  return (
    <>
      <section className="py-6">
        <AnimatedTitle text="GAA Fixtures & Results" />
        <p className="mt-2 text-sm text-gray-700">Fast, accessible, mobile-first coverage. Static data, zero bloat.</p>
      </section>
      <section className="mt-6">
        <h2 className="mb-2 text-lg font-semibold">This Weekends 4 Picks</h2>
        <Suspense fallback={<SkeletonList count={3} />}>{/* @ts-expect-error Async Server Component */}
          <WeekendPicks />
        </Suspense>
      </section>
      <section className="mt-6">
        <h2 className="mb-2 text-lg font-semibold">Last Weekends 4 Picks</h2>
        <Suspense fallback={<SkeletonList count={3} />}>{/* @ts-expect-error Async Server Component */}
          <PreviousWeekendPicks />
        </Suspense>
      </section>
    </>
  );
}
