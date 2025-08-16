import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

export function middleware(req: NextRequest) {
  const { pathname, search } = req.nextUrl
  if (pathname.startsWith('/graph')) {
    const token = req.cookies.get('access_token')?.value
    if (!token) {
      const url = new URL('/login', req.url)
      url.searchParams.set('next', `${pathname}${search || ''}`)
      return NextResponse.redirect(url)
    }
  }
  return NextResponse.next()
}

export const config = { matcher: ['/graph/:path*'] }