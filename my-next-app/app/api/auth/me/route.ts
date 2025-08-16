// app/api/auth/me/route.ts
import { NextRequest, NextResponse } from 'next/server'
export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const DJANGO_ME_PATH = process.env.DJANGO_ME_PATH || '/api/auth/users/me/'

function dj(path: string) {
  const base = process.env.DJANGO_BASE_URL
  if (!base) throw new Error('Missing DJANGO_BASE_URL')
  return `${base}${path}`
}

export async function GET(req: NextRequest) {
  try {
    const access =
      req.cookies.get('access_token')?.value ||
      req.cookies.get('access')?.value ||
      req.cookies.get('token')?.value

    if (!access) {
      return NextResponse.json({ ok: false, error: 'No token' }, { status: 401 })
    }

    const r = await fetch(dj(DJANGO_ME_PATH), {
      headers: { Authorization: `Bearer ${access}`, Accept: 'application/json' },
      cache: 'no-store',
    })

    const text = await r.text()
    let json: any = null
    try { json = JSON.parse(text) } catch {}
    if (!r.ok) return NextResponse.json({ ok: false, status: r.status, data: json ?? text }, { status: r.status })

    return NextResponse.json({ ok: true, data: json ?? text })
  } catch (e: any) {
    return NextResponse.json({ ok: false, error: e?.message || 'Server error' }, { status: 500 })
  }
}
