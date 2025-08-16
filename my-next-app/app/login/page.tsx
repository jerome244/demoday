// app/login/page.tsx
'use client'
import { useRouter, useSearchParams } from 'next/navigation'
import { useState } from 'react'

export default function LoginPage() {
  const router = useRouter()
  const next = useSearchParams().get('next') || '/graph'
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [status, setStatus] = useState('')

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setStatus('Signing in…')
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',            // ✅ ensure cookies are set on the browser
        body: JSON.stringify({ identifier, password }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data?.error || `Login failed (${res.status})`)

      // ✅ re-render server components with the new cookies
      router.replace(next)
      router.refresh()
    } catch (err: any) {
      setStatus(`❌ ${err.message || 'Login failed'}`)
      return
    }
    setStatus('✅ Signed in')
  }

  return (
    <main style={{ minHeight: '100svh', display: 'grid', placeItems: 'center', padding: 24 }}>
      <form onSubmit={onSubmit} style={{ width: 360, border: '1px solid #e5e7eb', borderRadius: 12, padding: 20 }}>
        <h1 style={{ margin: 0, fontSize: 24 }}>Login</h1>
        <label style={{ display: 'block', marginTop: 14 }}>Email or Username
          <input value={identifier} onChange={e => setIdentifier(e.target.value)} required style={{ width: '100%', marginTop: 6, padding: 8, border: '1px solid #e5e7eb', borderRadius: 8 }} />
        </label>
        <label style={{ display: 'block', marginTop: 12 }}>Password
          <input type="password" value={password} onChange={e => setPassword(e.target.value)} required style={{ width: '100%', marginTop: 6, padding: 8, border: '1px solid #e5e7eb', borderRadius: 8 }} />
        </label>
        <button type="submit" style={{ marginTop: 16, padding: '10px 14px', borderRadius: 8, background: '#111827', color: 'white', border: '1px solid transparent' }}>Sign in</button>
        <div role="status" aria-live="polite" style={{ marginTop: 10, minHeight: 20 }}>{status}</div>
      </form>
    </main>
  )
}