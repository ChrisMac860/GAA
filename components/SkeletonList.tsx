export default function SkeletonList({ count = 6 }: { count?: number }) {
  return (
    <div className="grid gap-3" aria-hidden="true">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="panel p-4">
          <div className="flex items-center justify-between">
            <div className="h-3 w-32 shimmer-bg animate-shimmer rounded" />
            <div className="h-3 w-12 shimmer-bg animate-shimmer rounded" />
          </div>
          <div className="mt-3 space-y-2">
            <div className="h-4 w-3/5 shimmer-bg animate-shimmer rounded" />
            <div className="h-4 w-2/5 shimmer-bg animate-shimmer rounded" />
          </div>
          <div className="mt-3 h-3 w-20 shimmer-bg animate-shimmer rounded" />
        </div>
      ))}
    </div>
  );
}
