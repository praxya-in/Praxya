'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'

function getSafeRedirect(path: string | null) {
  if (!path || !path.startsWith('/') || path.startsWith('//')) {
    return '/upload'
  }

  return path
}

export default function LoginPage() {
  const router = useRouter()
  const [redirectPath, setRedirectPath] = useState('/upload')

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    setRedirectPath(getSafeRedirect(params.get('redirect')))
  }, [])

  const handleSignIn = async () => {
    if (isLoading) return

    setIsLoading(true)
    setError(null)

    try {
      const supabase = createClient()
      const { error: signInError } = await supabase.auth.signInWithPassword({
        email,
        password,
      })

      if (signInError) {
        setError('Invalid email or password')
        return
      }

      router.replace(redirectPath)
    } catch {
      setError('Invalid email or password')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <main className="login-page">
      <div className="login-card">
        <h1 className="login-card__title">Welcome back</h1>
        <p className="login-card__subtitle">
          Sign in to continue to your compliance workspace.
        </p>

        <div className="login-card__field">
          <label className="login-card__label" htmlFor="email">
            Email
          </label>
          <input
            id="email"
            type="email"
            className="login-card__input"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@company.com"
            autoComplete="email"
          />
        </div>

        <div className="login-card__field">
          <label className="login-card__label" htmlFor="password">
            Password
          </label>
          <input
            id="password"
            type="password"
            className="login-card__input"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="Enter your password"
            autoComplete="current-password"
          />
        </div>

        {error && <p className="login-card__error">{error}</p>}

        <button
          type="button"
          className="btn btn--primary btn--lg login-card__button"
          onClick={handleSignIn}
          disabled={isLoading || !email || !password}
        >
          {isLoading ? (
            <>
              <span className="spinner spinner--sm" />
              Signing in…
            </>
          ) : (
            'Sign in'
          )}
        </button>
      </div>
    </main>
  )
}
