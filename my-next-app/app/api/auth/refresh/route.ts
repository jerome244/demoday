import { NextRequest, NextResponse } from 'next/server'
export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const REFRESH_PATH = process.env.SIMPLEJWT_REFRESH_PATH || '/api/token/refresh/'
function cookieOpts() {
  const prod = process.env.NODE_ENV === 'production'
  return { httpOnly: true, secure: prod, sameSite: 'lax' as const, path: '/' }
}
function dj(path: string) {
  const base = process.env.DJANGO_BASE_URL
  if (!base) throw new Error('Missing DJANGO_BASE_URL')
  return `${base}${path}`
}

export async function POST(req: NextRequest) {
  const refresh = req.cookies.get('refresh_token')?.value
  if (!refresh) return NextResponse.json({ error: 'No refresh token' }, { status: 401 })
  try {
    const r = await fetch(dj(REFRESH_PATH), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh }) })
    const text = await r.text(); let json: any = null; try { json = JSON.parse(text) } catch {}
    if (!r.ok) return NextResponse.json({ error: json?.detail || 'Refresh failed', backend: { status: r.status, body: json ?? text } }, { status: r.status })
    const access = json?.access || json?.token || json?.access_token
    const res = NextResponse.json({ ok: true })
    if (access) res.cookies.set('access_token', access, cookieOpts())
    return res
  } catch (e: any) {
    return NextResponse.json({ error: 'Network error to Django', detail: e?.message }, { status: 502 })
  }
}