// app/layout.tsx
import Link from 'next/link'
import './globals.css'
import { headers, cookies } from 'next/headers'
import { redirect } from 'next/navigation'

export const dynamic = 'force-dynamic'

async function getMe() {
  const base = process.env.NEXT_PUBLIC_BASE_PATH || ''
  try {
    const hdrs = await headers()
    const cookie = hdrs.get('cookie') ?? ''
    const r = await fetch(`${base}/api/auth/me`, { headers: { cookie }, cache: 'no-store' })
    if (!r.ok) return null
    const data = await r.json().catch(() => null)
    return data?.data || data?.user || data
  } catch { return null }
}

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const me = await getMe()

  // ✅ await cookies() and use .get(...)
  const ck = await cookies()
  const hasAuthCookie = ['access_token','refresh_token','access','refresh']
    .some((n) => Boolean(ck.get(n)))
  const isAuthed = Boolean(me) || hasAuthCookie

  // server action: logs out, clears cookies, redirects
  async function logout() {
    'use server'
    const base = process.env.NEXT_PUBLIC_BASE_PATH || ''
    const hdrs = await headers()
    const cookie = hdrs.get('cookie') ?? ''

    await fetch(`${base}/api/auth/logout`, {
      method: 'POST',
      headers: { cookie },
      cache: 'no-store',
    }).catch(() => {})

    // ✅ await cookies() here too
    const store = await cookies()
    ;['access','access_token','refresh','refresh_token','jwt','sessionid','csrftoken'].forEach(name => {
      try { store.delete(name) } catch {}
    })

    redirect('/login')
  }

  return (
    <html lang="en">
      <body style={{ margin: 0 }}>
        <header style={{ borderBottom: '1px solid #e5e7eb', padding: '12px 16px', display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <Link href="/" style={{ textDecoration: 'none', fontWeight: 700, color: '#111827' }}>Home</Link>
          <Link href="/graph" style={{ textDecoration: 'none', color: '#111827' }}>Graph</Link>

          {!isAuthed ? (
            <>
              <Link href="/login" style={{ textDecoration: 'none', color: '#111827' }}>Login</Link>
              <Link href="/register" style={{ textDecoration: 'none', color: '#111827' }}>Register</Link>
            </>
          ) : (
            <>
              {me && (
                <span style={{ marginLeft: 8, color: '#6b7280' }}>
                  {me.username || me.email}
                </span>
              )}
              <Link href="/account" style={{ textDecoration: 'none', color: '#111827', marginLeft: 8 }}>Account</Link>

              <div style={{ marginLeft: 'auto' }} />
              <form action={logout}>
                <button type="submit" style={{ border: '1px solid #e5e7eb', borderRadius: 8, padding: '6px 10px', background: 'white', cursor: 'pointer' }}>
                  Logout
                </button>
              </form>
            </>
          )}
        </header>
        <div>{children}</div>
      </body>
    </html>
  )
}
