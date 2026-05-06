import type { Metadata } from 'next'
import '@/styles/globals.css'
import '@/styles/upload.css'

export const metadata: Metadata = {
  title: 'Praxya — BRSR Compliance Platform',
  description:
    'AI-powered GHG accounting, SEBI BRSR Core compliance, and ESG reporting for Indian specialty chemical manufacturers.',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;600&family=DM+Mono:wght@400;500&family=DM+Serif+Display:ital@0;1&family=Instrument+Sans:wght@400;500;600&display=swap" rel="stylesheet" />
      </head>
      <body>{children}</body>
    </html>
  )
}
