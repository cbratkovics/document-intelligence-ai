import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

const SITE_URL = "https://frontend-doc-intel.vercel.app";
const TITLE = "Document Intelligence demo";
const DESCRIPTION =
  "Hybrid BM25 and dense retrieval over a small corpus, with every passage's BM25, dense and fused ranks shown side by side. Retrieval only; no language model is called.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: TITLE,
  description: DESCRIPTION,
  openGraph: {
    type: "website",
    url: "/",
    siteName: TITLE,
    title: "Hybrid retrieval that shows its evidence",
    description: DESCRIPTION,
    images: [
      {
        url: "/og.png",
        width: 1200,
        height: 630,
        alt: "The evidence view: a top passage with matched terms highlighted and a ranked list with BM25, dense and fused ranks",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Hybrid retrieval that shows its evidence",
    description: DESCRIPTION,
    images: ["/og.png"],
  },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
