// app/api/auth/register/route.ts
import { NextRequest, NextResponse } from 'next/server'
export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const REGISTER_PATH = process.env.DJANGO_REGISTER_PATH || '/api/auth/users/'

function dj(path: string) {
  const base = process.env.DJANGO_BASE_URL
  if (!base) throw new Error('Missing DJANGO_BASE_URL')
  return `${base}${path}`
}

async function trySend(payload: any) {
  try {
    const r = await fetch(dj(REGISTER_PATH), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const text = await r.text(); let json: any = null; try { json = JSON.parse(text) } catch {}
    return { ok: r.ok, status: r.status, json, text }
  } catch (e: any) {
    return { ok: false, status: 0, json: null, text: `Network error: ${e?.message || String(e)}` }
  }
}

export async function POST(req: NextRequest) {
  try {
    const incoming = (await req.json().catch(() => ({}))) as any
    const candidates: any[] = []

    // 1) pass-through (expects username + password, optional email)
    candidates.push(incoming)

    // 2) if missing username but email present, derive username
    if (!incoming.username && incoming.email && incoming.password) {
      const uname = String(incoming.email).split('@')[0]
      candidates.push({ username: uname, email: incoming.email, password: incoming.password })
    }

    let firstBad: any = null
    for (const p of candidates) {
      const info = await trySend(p)
      if (info.ok) return NextResponse.json({ ok: true, data: info.json ?? info.text })
      if (!firstBad) firstBad = info
      if (info.status && ![400, 401, 422].includes(info.status)) break
    }
    return NextResponse.json({ error: 'Registration failed', backend: firstBad }, { status: firstBad?.status || 500 })
  } catch (e: any) {
    return NextResponse.json({ error: e?.message || 'Server error' }, { status: 500 })
  }
}


export async function GET() {
  return NextResponse.json({ ok: true, route: '/api/auth/register' });
}
