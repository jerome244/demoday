// components/Header.tsx
import Link from 'next/link'
import { cookies, headers as nextHeaders } from 'next/headers'
import { redirect } from 'next/navigation'

export const dynamic = 'force-dynamic'        // render per-request
export const fetchCache = 'default-no-store'  // avoid caching the /me check

async function isLoggedIn(): Promise<boolean> {
  // quick cookie presence check (works for jwt or session auth)
  const ck = cookies()
  const hasAnyAuthCookie =
    ck.has('access') || ck.has('access_token') || ck.has('refresh') ||
    ck.has('jwt') || ck.has('sessionid')

  // verify by asking our own API (for correctness across cookie names)
  try {
    const h = await nextHeaders()
    const res = await fetch(`${process.env.NEXT_PUBLIC_BASE_PATH || ''}/api/auth/me`, {
      headers: { cookie: h.get('cookie') ?? '' },
      cache: 'no-store',
    })
    if (res.ok) return true
  } catch {}

  return hasAnyAuthCookie
}

export default async function Header() {
  const loggedIn = await isLoggedIn()

  async function logout() {
    'use server'
    await fetch(`${process.env.NEXT_PUBLIC_BASE_PATH || ''}/api/auth/logout`, {
      method: 'POST',
      cache: 'no-store',
    })
    redirect('/') // back to home after logout
  }

  return (
    <header style={{ borderBottom: '1px solid #e5e7eb', padding: '12px 16px', display: 'flex', gap: 12, flexWrap: 'wrap' }}>
      <Link href="/" style={{ textDecoration: 'none', fontWeight: 700, color: '#111827' }}>Home</Link>
      <Link href="/graph" style={{ textDecoration: 'none', color: '#111827' }}>Graph</Link>

      {!loggedIn ? (
        <>
          <Link href="/login" style={{ textDecoration: 'none', color: '#111827' }}>Login</Link>
          <Link href="/register" style={{ textDecoration: 'none', color: '#111827' }}>Register</Link>
        </>
      ) : (
        <>
          <Link href="/account" style={{ textDecoration: 'none', color: '#111827' }}>Account</Link>
          <form action={logout} style={{ marginLeft: 'auto' }}>
            <button type="submit" style={{ border: '1px solid #e5e7eb', borderRadius: 8, padding: '6px 10px', background: 'white' }}>
              Logout
            </button>
          </form>
        </>
      )}
    </header>
  )
}
