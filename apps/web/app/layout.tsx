import type { Metadata } from 'next'
import '@/styles/globals.css'

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
      <body>{children}</body>
    </html>
  )
}
