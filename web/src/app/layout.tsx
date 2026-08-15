import type { Metadata } from "next";
import { Space_Grotesk, JetBrains_Mono } from "next/font/google";
import "katex/dist/katex.min.css";
// Self-hosted OpenDyslexic (OFL). Declaring the @font-face costs nothing on
// its own — the browser only fetches the files once a rule actually uses the
// family, i.e. when the reading toggle is on.
import "@fontsource/opendyslexic/400.css";
import "@fontsource/opendyslexic/400-italic.css";
import "@fontsource/opendyslexic/700.css";
import "@fontsource/opendyslexic/700-italic.css";
import "./globals.css";
import AppShell from "@/components/AppShell";
import ThemeProvider from "@/components/ThemeProvider";

const spaceGrotesk = Space_Grotesk({ subsets: ["latin"], variable: "--font-space-grotesk" });
const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["300", "400", "500"],
  variable: "--font-jetbrains-mono",
});

export const metadata: Metadata = {
  title: { default: "Study Buddy", template: "%s · Study Buddy" },
  description: "A private, local-first workspace for notes, lectures, and focused study.",
};

// Applies stored theme/accent/grid/reading preferences to <html> before paint
// so the first render matches the saved appearance (no light-mode flash, and
// no reflow from a late font swap).
const themeBootstrap = `try{var p=JSON.parse(localStorage.getItem('axiom-prefs')||'{}');document.documentElement.setAttribute('data-theme',p.theme||'dark');if(p.accent)document.documentElement.style.setProperty('--accent',p.accent);document.documentElement.style.setProperty('--grid-opacity',p.grid===false?'0':'0.35');if(p.dyslexic===true)document.documentElement.setAttribute('data-dyslexic','true');}catch(e){}`;

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      data-theme="dark"
      suppressHydrationWarning
      className={`${spaceGrotesk.variable} ${jetbrainsMono.variable} h-full antialiased`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootstrap }} />
      </head>
      <body className="min-h-full text-[15px]">
        <ThemeProvider>
          <AppShell>{children}</AppShell>
        </ThemeProvider>
      </body>
    </html>
  );
}
