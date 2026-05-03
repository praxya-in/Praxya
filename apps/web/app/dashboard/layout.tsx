import Sidebar from './components/Sidebar'

export const metadata = {
  title: 'Dashboard — Praxya',
  description: 'Overview of GHG footprint and audit metrics.',
}

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: 'var(--bg-primary)' }}>
      <Sidebar />
      <main style={{ flex: 1, overflowY: 'auto' }}>
        {children}
      </main>
    </div>
  )
}
