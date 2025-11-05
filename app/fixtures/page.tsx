import { Suspense } from "react";
import SkeletonList from "@/components/SkeletonList";
import { loadFixtures, type Fixture } from "@/lib/data";
import FixturesSearch from "@/components/FixturesSearch";

export const metadata = {
  title: "Fixtures",
  description: "Search fixtures (Irish or English)"
};

export const dynamic = "force-dynamic";

async function FixturesBody({ q }: { q: string }) {
  await new Promise((r) => setTimeout(r, 320));
  const fixtures = await loadFixtures();
  return <FixturesSearch fixtures={fixtures} initialQuery={q} />;
}

export default async function Page({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const sp = await searchParams;
  const q = (sp?.q ?? "").toString();
  return (
    <section className="space-y-3">
      <div className="flex items-end justify-between">
        <h1 className="text-lg font-semibold">Fixtures</h1>
      </div>
      <Suspense fallback={<SkeletonList count={6} />}> 
        {/* @ts-expect-error Async Server Component */}
        <FixturesBody q={q} />
      </Suspense>
    </section>
  );
}
