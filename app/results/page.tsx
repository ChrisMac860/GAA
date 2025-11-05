import { Suspense } from "react";
import SkeletonList from "@/components/SkeletonList";
import ResultsSearch from "@/components/ResultsSearch";
import { loadResults } from "@/lib/data";

export const metadata = {
  title: "Results",
  description: "Recent GAA results (last 7 days)",
};

export const dynamic = "force-dynamic";

async function ResultsBody({ q }: { q: string }) {
  await new Promise((r) => setTimeout(r, 320));
  const items = await loadResults();
  return <ResultsSearch results={items} initialQuery={q} />;
}

export default async function Page({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const sp = await searchParams;
  const q = (sp?.q ?? "").toString();
  return (
    <section className="space-y-3">
      <div className="flex items-end justify-between">
        <h1 className="text-lg font-semibold">Results</h1>
      </div>
      <Suspense fallback={<SkeletonList count={6} />}> 
        {/* @ts-expect-error Async Server Component */}
        <ResultsBody q={q} />
      </Suspense>
    </section>
  );
}

