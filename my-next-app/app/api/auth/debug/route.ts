import { NextResponse } from 'next/server'
export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

function dj(path: string) {
  const base = process.env.DJANGO_BASE_URL
  if (!base) throw new Error('Missing DJANGO_BASE_URL')
  return `${base}${path}`
}

async function tryFetch(url: string, init?: RequestInit) {
  try {
    const r = await fetch(url, { ...init, cache: 'no-store' })
    const text = await r.text()
    let json: any = null; try { json = JSON.parse(text) } catch {}
    return { ok: r.ok, status: r.status, headers: Object.fromEntries(r.headers.entries()), json, text }
  } catch (e: any) {
    return { ok: false, status: 0, error: e?.message || String(e) }
  }
}

export async function GET() {
  try {
    const base = process.env.DJANGO_BASE_URL
    const mode = (process.env.AUTH_MODE || 'jwt').toLowerCase()
    if (!base) return NextResponse.json({ ok: false, error: 'Missing DJANGO_BASE_URL' }, { status: 500 })

    const ping = await tryFetch(base)
    const tokenPath = process.env.SIMPLEJWT_TOKEN_PATH || '/api/token/'
    const registerPath = process.env.DJANGO_REGISTER_PATH || '/api/users/'
    const mePath = process.env.DJANGO_ME_PATH || '/api/users/me/'

    const tokenHead = await tryFetch(dj(tokenPath), { method: 'OPTIONS' })
    const regOptions = await tryFetch(dj(registerPath), { method: 'OPTIONS' })
    const meGet = await tryFetch(dj(mePath))

    return NextResponse.json({
      ok: true,
      env: { DJANGO_BASE_URL: base, AUTH_MODE: mode, tokenPath, registerPath, mePath },
      reachability: { base: ping, token: tokenHead, register: regOptions, me: meGet },
    })
  } catch (e: any) {
    return NextResponse.json({ ok: false, error: e?.message || 'debug failed' }, { status: 500 })
  }
}