import type { Metadata } from "next";
import { IBM_Plex_Sans, Rubik } from "next/font/google";

import "@copilotkit/react-ui/styles.css";
import "./globals.css";

const bodyFont = IBM_Plex_Sans({
  subsets: ["latin", "cyrillic"],
  variable: "--font-body",
  weight: ["400", "500", "600"],
});

const displayFont = Rubik({
  subsets: ["latin", "cyrillic"],
  variable: "--font-display",
  weight: ["500", "700"],
});

export const metadata: Metadata = {
  title: "OR Student Chat",
  description: "Semantics-driven educational chat over typed OR extensions.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ru">
      <body className={`${bodyFont.variable} ${displayFont.variable}`}>
        {children}
      </body>
    </html>
  );
}
