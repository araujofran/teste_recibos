import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "OCR Validation Lab",
  description: "Dashboard for OCR Receipt Extraction Validation",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="bg-slate-50 text-slate-900 min-h-screen font-sans antialiased">
        <div className="flex h-screen overflow-hidden">
          {/* Sidebar */}
          <aside className="w-64 bg-slate-900 text-slate-300 flex flex-col">
            <div className="p-4 bg-slate-950 text-white font-bold text-xl border-b border-slate-800">
              OCR Lab
            </div>
            <nav className="flex-1 p-4 space-y-2">
              <a href="/" className="block py-2 px-3 rounded hover:bg-slate-800 hover:text-white transition-colors bg-slate-800 text-white">Dashboard</a>
              <a href="/upload" className="block py-2 px-3 rounded hover:bg-slate-800 hover:text-white transition-colors">Upload / Test</a>
              <a href="/review" className="block py-2 px-3 rounded hover:bg-slate-800 hover:text-white transition-colors">Human Review</a>
              <a href="/metrics" className="block py-2 px-3 rounded hover:bg-slate-800 hover:text-white transition-colors">Metrics</a>
            </nav>
          </aside>
          
          {/* Main content */}
          <main className="flex-1 overflow-y-auto p-8">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
