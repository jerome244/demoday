import { NextRequest, NextResponse } from 'next/server'
export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const AUTH_MODE = (process.env.AUTH_MODE || 'jwt').toLowerCase()
const TOKEN_PATH = process.env.SIMPLEJWT_TOKEN_PATH || '/api/token/'
const ME_PATH = process.env.DJANGO_ME_PATH || '/api/users/me/'

function cookieOpts() {
  const prod = process.env.NODE_ENV === 'production'
  return { httpOnly: true, secure: prod, sameSite: 'lax' as const, path: '/' }
}
function dj(path: string) {
  const base = process.env.DJANGO_BASE_URL
  if (!base) throw new Error('Missing DJANGO_BASE_URL')
  return `${base}${path}`
}
async function parse(res: Response) {
  const text = await res.text(); let json: any = null; try { json = JSON.parse(text) } catch {}
  return { ok: res.ok, status: res.status, json, text }
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json().catch(() => ({})) as any
    const identifier: string = body.identifier
    const password: string = body.password
    if (!identifier || !password) return NextResponse.json({ error: 'Missing credentials' }, { status: 400 })

    if (AUTH_MODE === 'jwt') {
      // Try username or email
      const tries = [ { username: identifier, password }, { email: identifier, password } ]
      let last: any = null
      for (const payload of tries) {
        let info
        try {
          const r = await fetch(dj(TOKEN_PATH), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
          info = await parse(r)
        } catch (e: any) {
          return NextResponse.json({ error: 'Network error to Django', detail: e?.message }, { status: 502 })
        }
        if (info.ok) {
          const data: any = info.json || {}
          const access = data.access || data.token || data.access_token
          const refresh = data.refresh || data.refresh_token
          if (!access) return NextResponse.json({ error: 'No access token in Django response', backend: info }, { status: 502 })
          const res = NextResponse.json({ ok: true })
          res.cookies.set('access_token', access, cookieOpts())
          if (refresh) res.cookies.set('refresh_token', refresh, cookieOpts())
          // Optional: current user
          try {
            const me = await fetch(dj(ME_PATH), { headers: { Authorization: `Bearer ${access}` }, cache: 'no-store' })
            if (me.ok) {
              const meInfo = await parse(me)
              return NextResponse.json({ ok: true, user: meInfo.json ?? meInfo.text }, { headers: res.headers })
            }
          } catch {}
          return res
        }
        last = info
        if (![400, 401, 422].includes(info.status)) break
      }
      return NextResponse.json({ error: 'Invalid credentials', backend: last }, { status: last?.status || 401 })
    }

    // SESSION mode (optional)
    try {
      const r = await fetch(dj('/accounts/login/'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: identifier, password }), redirect: 'manual' })
      const info = await parse(r)
      const res = NextResponse.json({ ok: info.ok, backend: { status: info.status, body: info.json ?? info.text } })
      const setCookie = r.headers.get('set-cookie'); if (setCookie) res.headers.set('set-cookie', setCookie)
      return res
    } catch (e: any) {
      return NextResponse.json({ error: 'Network error to Django', detail: e?.message }, { status: 502 })
    }
  } catch (e: any) {
    return NextResponse.json({ error: e?.message || 'Server error' }, { status: 500 })
  }
}