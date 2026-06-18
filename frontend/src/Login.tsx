import { useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError } from './api'
import { login, register } from './auth'
import { useAuth } from './auth-context'
import './Login.css'

export default function Login() {
  const navigate = useNavigate()
  const { refresh } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function handleSubmit(event: FormEvent, mode: 'login' | 'register') {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      if (mode === 'register') {
        await register(email, password)
      }
      await login(email, password)
      await refresh()
      navigate('/')
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail)
      } else {
        setError('Something went wrong. Is the server running?')
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth-screen">
      <div className="card auth-card">
        <div className="auth-brand">
          <div className="auth-mark">B</div>
          <div className="auth-wordmark">Blogger</div>
        </div>

        <h1 className="auth-title">Write posts in your brand’s voice</h1>
        <p className="auth-sub">
          Sign in to brief Blogger and get a polished post, quality-checked.
        </p>

        <form className="auth-form" onSubmit={(e) => handleSubmit(e, 'login')}>
          <label className="auth-label">
            Email
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@brand.com"
              autoComplete="email"
              required
            />
          </label>

          <label className="auth-label">
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              autoComplete="current-password"
              required
            />
          </label>

          {error && <div className="auth-error">{error}</div>}

          <div className="auth-actions">
            <button
              type="button"
              className="btn btn-ghost"
              disabled={busy}
              onClick={(e) => handleSubmit(e, 'register')}
            >
              Create account
            </button>
            <button type="submit" className="btn btn-primary" disabled={busy}>
              {busy ? 'Please wait…' : 'Sign in'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
