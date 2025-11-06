import type { Metadata, Viewport } from "next";
import Link from "next/link";
import "@/styles/globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://gaa-fixtures.local"),
  title: {
    default: "GAA Fixtures & Results",
    template: "%s · GAA Fixtures"
  },
  description: "Fast, accessible GAA fixtures and results.",
  openGraph: {
    title: "GAA Fixtures & Results",
    description: "Fast, accessible GAA fixtures and results.",
    url: "/",
    siteName: "GAA Fixtures",
    type: "website"
  },
  icons: {
    icon: "/favicon.ico"
  }
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full">
      <body className="min-h-screen font-sans selection:bg-blue-100 selection:text-blue-900">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus-ring fixed left-2 top-2 z-50 rounded bg-white px-3 py-2 text-sm"
        >
          Skip to content
        </a>
        <header className="sticky top-0 z-40 strip">
          <div className="mx-auto flex max-w-screen-sm items-center justify-between gap-3 px-4 py-3">
            <Link href="/" className="text-base font-extrabold tracking-tight">GAA Fixtures</Link>
            <nav aria-label="Primary" className="ml-auto flex items-center gap-2">
              <Link href="/fixtures" className="btn btn-secondary text-sm">Fixtures</Link>
              <Link href="/results" className="btn btn-secondary text-sm">Results</Link>
            </nav>
          </div>
        </header>
        <main id="main" className="mx-auto max-w-screen-sm px-4 pb-24 pt-3">
          {children}
        </main>
        <footer className="mt-8 border-t border-black/20 bg-blue-50">
          <div className="mx-auto max-w-screen-sm px-4 py-4 flex items-center justify-between">
            <p className="text-xs text-black/80">Built for speed and clarity.</p>
            <a
              href="https://buymeacoffee.com/christopheosp"
              target="_blank"
              rel="noopener noreferrer"
              className="btn btn-primary text-xs"
            >
              Buy me a beer
            </a>
          </div>
        </footer>
      </body>
    </html>
  );
}
