import "./globals.css";
import type { Metadata } from "next";
import { Open_Sans } from "next/font/google";

/** Self-hosted at build, like the PDF worker. Nothing loads from a CDN. */
const openSans = Open_Sans({
  subsets: ["latin"],
  weight: ["400", "600", "700"],
  display: "swap",
  variable: "--font-open-sans",
});

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
    <html lang="en" className={openSans.variable} suppressHydrationWarning>
      <body
        className="bg-ground font-sans text-body text-ink"
        suppressHydrationWarning
      >
        {children}
      </body>
    </html>
  );
}
