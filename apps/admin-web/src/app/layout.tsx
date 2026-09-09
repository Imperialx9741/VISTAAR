import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "VISTAAR Admin",
  description: "Operations console for the VISTAAR ride-hailing platform.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      {/* suppressHydrationWarning here (not a broader/riskier fix) —
          this is React's own documented mechanism for exactly this
          case (see Next.js's own hydration-error docs, "It can also
          happen if the client has a browser extension installed which
          messes with the HTML before React loaded"): a browser
          extension (Grammarly, confirmed by its own signature
          data-gr-ext-installed/data-new-gr-c-s-check-loaded
          attributes) injects attributes onto <body> before React
          hydrates. It only silences a mismatch on this element's own
          attributes — a real hydration mismatch inside `children`
          still surfaces normally. */}
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
