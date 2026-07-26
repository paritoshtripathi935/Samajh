import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Samajh · समझ — Filing-Understanding Workbench',
  description:
    'Digitise a legal filing and ask questions over it — every answer is cited and jumps to the exact source span, with low-confidence extractions flagged.',
};

// Set `data-theme` before first paint so there is no light/dark flash.
const noFlashTheme = `(function(){try{var k='samajh:theme';var s=localStorage.getItem(k);var m=window.matchMedia&&window.matchMedia('(prefers-color-scheme: light)').matches?'light':'dark';var t=(s==='light'||s==='dark')?s:(s==='system'?m:'dark');document.documentElement.setAttribute('data-theme',t);}catch(e){document.documentElement.setAttribute('data-theme','dark');}})();`;

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <head>
        {/* Inter (UI chrome) + Source Serif 4 (content + brand) + JetBrains Mono (citations). */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Source+Serif+4:opsz,wght@8..60,400;8..60,500;8..60,600;8..60,700&family=JetBrains+Mono:wght@400;500&display=swap"
        />
        <script dangerouslySetInnerHTML={{ __html: noFlashTheme }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
