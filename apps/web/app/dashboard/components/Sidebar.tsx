'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useState } from 'react'
import { createClient } from '@/lib/supabase/client'

export default function Sidebar() {
  const pathname = usePathname()
  const [email, setEmail] = useState<string | null>(null)

  useEffect(() => {
    const supabase = createClient()
    supabase.auth.getUser().then(({ data }) => {
      if (data?.user?.email) {
        setEmail(data.user.email)
      }
    })
  }, [])

  const navItems = [
    { name: 'Overview', href: '/dashboard', icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>
    ), comingSoon: false },
    { name: 'GHG Footprint', href: '/dashboard/ghg', icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"></path></svg>
    ), comingSoon: false },
    { name: 'Water', href: '/dashboard/water', icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22a7 7 0 0 0 7-7c0-2-1-3.9-3-5.5s-3.5-4-4-6.5c-.5 2.5-2 4.9-4 6.5C6 11.1 5 13 5 15a7 7 0 0 0 7 7z"></path></svg>
    ), comingSoon: true },
    { name: 'Energy', href: '/dashboard/energy', icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg>
    ), comingSoon: true },
    { name: 'Circularity', href: '/dashboard/circ', icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"></path><path d="M3 3v5h5"></path></svg>
    ), comingSoon: true },
    { name: 'CBAM Export', href: '/dashboard/cbam', icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg>
    ), comingSoon: true },
    { name: 'Audit Trail', href: '/dashboard/audit', icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>
    ), comingSoon: false },
  ]

  return (
    <div style={{
      width: '240px',
      background: 'var(--bg-secondary)',
      borderRight: '1px solid var(--border)',
      display: 'flex',
      flexDirection: 'column',
      height: '100%'
    }}>
      <div style={{
        padding: '24px 20px',
        borderBottom: '1px solid var(--border)',
        display: 'flex',
        alignItems: 'center',
        gap: '12px'
      }}>
        <svg width="28" height="28" viewBox="0 0 24 24" fill="#22c55e">
          <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
        </svg>
        <span style={{
          fontFamily: 'var(--font-serif)',
          fontSize: '22px',
          color: 'var(--white)'
        }}>
          praxya
        </span>
      </div>

      <nav style={{
        flex: 1,
        padding: '20px 12px',
        display: 'flex',
        flexDirection: 'column',
        gap: '4px'
      }}>
        {navItems.map((item) => {
          const isActive = pathname === item.href || (item.href !== '/dashboard' && pathname.startsWith(item.href))
          
          return (
            <Link key={item.name} href={item.href} style={{
              display: 'flex',
              alignItems: 'center',
              padding: '10px 20px',
              borderRadius: '6px',
              fontFamily: 'var(--font-sans)',
              fontSize: '14px',
              textDecoration: 'none',
              background: isActive ? 'var(--green-glow)' : 'transparent',
              color: isActive ? 'var(--green)' : (item.comingSoon ? 'var(--white-muted)' : 'var(--white-dim)'),
              borderLeft: isActive ? '2px solid var(--green)' : '2px solid transparent',
              transition: 'all 0.2s'
            }}
            onMouseEnter={(e) => {
              if (!isActive && !item.comingSoon) {
                e.currentTarget.style.background = 'rgba(255,255,255,0.04)'
                e.currentTarget.style.color = 'var(--white)'
              }
            }}
            onMouseLeave={(e) => {
              if (!isActive) {
                e.currentTarget.style.background = 'transparent'
                e.currentTarget.style.color = item.comingSoon ? 'var(--white-muted)' : 'var(--white-dim)'
              }
            }}>
              <span style={{ marginRight: '12px', display: 'flex' }}>
                {item.icon}
              </span>
              {item.name}
              {item.comingSoon && (
                <span style={{
                  fontSize: '9px',
                  background: 'rgba(245,158,11,0.15)',
                  color: 'var(--amber)',
                  borderRadius: '4px',
                  padding: '1px 5px',
                  marginLeft: '8px',
                  fontFamily: 'var(--font-mono)'
                }}>
                  Coming soon
                </span>
              )}
            </Link>
          )
        })}
      </nav>

      <div style={{
        borderTop: '1px solid var(--border)',
        padding: '16px 20px',
        fontFamily: 'var(--font-mono)',
        fontSize: '12px',
        color: 'var(--white-muted)',
        whiteSpace: 'nowrap',
        overflow: 'hidden',
        textOverflow: 'ellipsis'
      }}>
        {email || 'Loading...'}
      </div>
    </div>
  )
}
