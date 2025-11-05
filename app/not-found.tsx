import Link from "next/link";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-screen-sm py-16 text-center">
      <h2 className="text-2xl font-bold">Page not found</h2>
      <p className="mt-2 text-gray-700">Sorry, we couldn’t find that page.</p>
      <Link
        href="/"
        className="mt-6 inline-flex min-h-[44px] items-center justify-center rounded-lg bg-blue-600 px-4 py-2 font-medium text-white"
      >
        Back to Today
      </Link>
    </div>
  );
}

