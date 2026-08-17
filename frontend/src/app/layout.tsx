import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Manual Assist",
  description: "Answers from large manuals, with the page they came from",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    // Extensions inject attributes on <html> and <body> before React loads,
    // which otherwise reports a hydration mismatch that is not ours.
    <html lang="en" suppressHydrationWarning>
      <body
        className="bg-slate-100 text-slate-900"
        suppressHydrationWarning
      >
        {children}
      </body>
    </html>
  );
}