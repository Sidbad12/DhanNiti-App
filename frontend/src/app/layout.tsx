import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "DhanNiti | AI Quant Portfolio Intelligence",
  description: "Institutional-grade NSE portfolio optimization powered by XGBoost, Prophet, and Groq LLM. Real-time AI advisory with episodic memory.",
  keywords: "NSE, portfolio, AI, quant, XGBoost, Prophet, trading, India",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrainsMono.variable} h-full`}>
      <body className="min-h-full bg-[#070a0f] antialiased">{children}</body>
    </html>
  );
}
