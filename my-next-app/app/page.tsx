// app/page.tsx (Server Component)
import Link from 'next/link'
import { headers, cookies } from 'next/headers'   // ⬅ add cookies

export const dynamic = 'force-dynamic'

// same getMe as you had
async function getMe() {
  const base = process.env.NEXT_PUBLIC_BASE_PATH || ''
  try {
    const hdrs = await headers()
    const cookie = hdrs.get('cookie') ?? ''
    const r = await fetch(`${base}/api/auth/me`, {
      headers: { cookie },
      cache: 'no-store',
    })
    if (!r.ok) return null
    const data = await r.json().catch(() => null)
    return data?.data || data?.user || data
  } catch {
    return null
  }
}

export default async function Home({
  searchParams,
}: {
  // Next’s dynamic APIs: await searchParams
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  const me = await getMe()

  // ✅ cookie fallback so buttons hide even if /me hiccups
  const ck = await cookies()
  const hasAuthCookie = ['access_token','refresh_token','access','refresh'].some(n => ck.get(n))
  const isAuthed = Boolean(me?.id || me?.email || me?.username) || hasAuthCookie

  const sp = await searchParams
  const next =
    typeof sp?.next === 'string'
      ? sp.next
      : Array.isArray(sp?.next) && sp.next.length
      ? sp.next[0]
      : '/graph'

  // If you prefer sending logged-in users away from home:
  // if (isAuthed) redirect('/graph')

  return (
    <main style={{ minHeight: '100svh', display: 'grid', placeItems: 'center', padding: 24 }}>
      <div style={{ textAlign: 'center', maxWidth: 640 }}>
        <h1 style={{ margin: 0, fontSize: 32 }}>Code Graph Explorer</h1>
        <p style={{ color: '#6b7280', marginTop: 8 }}>
          Upload a project ZIP and visualize functions and imports across files.
        </p>

        <Link
          href={next}
          style={{
            display: 'inline-block',
            marginTop: 16,
            border: '1px solid #111827',
            borderRadius: 10,
            padding: '10px 14px',
            textDecoration: 'none',
          }}
        >
          Open Graph Tool
        </Link>

        {!isAuthed && (
          <div style={{ marginTop: 18, display: 'flex', gap: 16, justifyContent: 'center' }}>
            <Link href="/login" style={{ textDecoration: 'none', border: '1px solid #e5e7eb', borderRadius: 8, padding: '8px 12px' }}>
              Login
            </Link>
            <Link href="/register" style={{ textDecoration: 'none', border: '1px solid #e5e7eb', borderRadius: 8, padding: '8px 12px' }}>
              Register
            </Link>
          </div>
        )}
      </div>
    </main>
  )
}
