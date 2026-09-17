import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

/**
 * This runs on one laptop for one reader, so the upstream project's public-web chrome is
 * gone: no structured data, no canonical host, no analytics or speed-insights beacons.
 * Papers get pasted in here before they are public knowledge, and nothing about that
 * should leave the machine.
 */

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: {
    default: "Paper in Five",
    template: "%s · Paper in Five",
  },
  description:
    "Turns an open-access PubMed paper into a scrollable explainer, with every plotted number checked against the paper's own text.",
  applicationName: "Paper in Five",
  robots: { index: false, follow: false },
  icons: {
    icon: [{ url: "/icon.png", type: "image/png" }],
    apple: [{ url: "/icon.png", type: "image/png" }],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    // globals.css sets scroll-behavior: smooth; Next wants that declared so it can
    // suppress it during route transitions.
    <html lang="en" data-scroll-behavior="smooth">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased min-h-dvh bg-black text-[#e8e8e8]`}
      >
        <div className="min-h-dvh">{children}</div>
      </body>
    </html>
  );
}
