import type { NextRequest } from 'next/server'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const API_PROXY_TARGET = (process.env.API_PROXY_TARGET || 'http://127.0.0.1:8005').replace(/\/$/, '')
const HOP_BY_HOP_HEADERS = [
  'connection',
  'content-length',
  'host',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailer',
  'transfer-encoding',
  'upgrade',
]

type ProxyContext = { params: { path: string[] } }
type StreamingRequestInit = RequestInit & { duplex?: 'half' }

async function proxy(request: NextRequest, context: ProxyContext) {
  const target = new URL(`${API_PROXY_TARGET}/api/${context.params.path.join('/')}`)
  target.search = request.nextUrl.search

  const requestHeaders = new Headers(request.headers)
  const contentLength = request.headers.get('content-length')
  const hasTransferEncoding = request.headers.has('transfer-encoding')
  HOP_BY_HOP_HEADERS.forEach(header => requestHeaders.delete(header))

  const init: StreamingRequestInit = {
    method: request.method,
    headers: requestHeaders,
    redirect: 'manual',
    cache: 'no-store',
  }
  const hasRequestBody = request.body && (
    (contentLength !== null && contentLength !== '0') || hasTransferEncoding
  )
  if (request.method !== 'GET' && request.method !== 'HEAD' && hasRequestBody) {
    init.body = request.body
    init.duplex = 'half'
  }

  const upstream = await fetch(target, init)
  const responseHeaders = new Headers(upstream.headers)
  HOP_BY_HOP_HEADERS.forEach(header => responseHeaders.delete(header))
  responseHeaders.set('Cache-Control', 'no-cache, no-store, no-transform')
  if (responseHeaders.get('content-type')?.includes('text/event-stream')) {
    responseHeaders.set('X-Accel-Buffering', 'no')
  }

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  })
}

export const GET = proxy
export const POST = proxy
export const PUT = proxy
export const PATCH = proxy
export const DELETE = proxy
export const OPTIONS = proxy
