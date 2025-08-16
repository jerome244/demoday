import { NextRequest, NextResponse } from 'next/server'
export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const LOGOUT_PATH = process.env.DJANGO_LOGOUT_PATH || '/api/logout/'
const AUTH_MODE = (process.env.AUTH_MODE || 'jwt').toLowerCase()
function cleared() {
  const res = NextResponse.json({ ok: true })
  res.cookies.set('access_token', '', { path: '/', httpOnly: true, maxAge: 0 })
  res.cookies.set('refresh_token', '', { path: '/', httpOnly: true, maxAge: 0 })
  return res
}
function dj(path: string) {
  const base = process.env.DJANGO_BASE_URL
  if (!base) throw new Error('Missing DJANGO_BASE_URL')
  return `${base}${path}`
}

export async function POST(_req: NextRequest) {
  if (AUTH_MODE === 'jwt') return cleared()
  try { await fetch(dj(LOGOUT_PATH), { method: 'POST' }); return cleared() } catch { return cleared() }
}