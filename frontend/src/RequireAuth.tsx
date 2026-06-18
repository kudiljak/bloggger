import { Navigate } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useAuth } from './auth-context'

export default function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()

  if (loading) {
    return <div className="auth-screen">Loading…</div>
  }

  if (user === null) {
    return <Navigate to="/login" replace />
  }

  return <>{children}</>
}
