import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { PromptProvider } from "./context/PromptContext";
import { ExecutionProvider } from "@/app/context/ExecutionContext";
import { SessionProvider } from "@/components/providers/SessionProvider";
import { ConvexClientProvider } from "@/components/providers/ConvexProvider";
import { ThemeProvider } from "@/components/providers/ThemeProvider";
const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Autonomous AI Software Team",
  description: "Building the future of software development, autonomously.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased min-h-screen bg-background text-foreground transition-colors`}
      >
        <ThemeProvider>
          <SessionProvider>
            {/* <ConvexClientProvider> */}
            <ExecutionProvider>
              <PromptProvider>{children}</PromptProvider>
            </ExecutionProvider>
            {/* </ConvexClientProvider> */}
          </SessionProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
