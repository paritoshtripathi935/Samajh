import { type NextRequest } from 'next/server';

const BACKEND_URL =
  process.env.BACKEND_URL?.trim() ||
  process.env.NEXT_PUBLIC_BACKEND_URL?.trim() ||
  'http://127.0.0.1:8000';

type Context = {
  params: Promise<{ path: string[] }>;
};

async function proxy(request: NextRequest, context: Context) {
  const { path } = await context.params;
  const target = new URL(`/api/${path.join('/')}`, BACKEND_URL);
  target.search = request.nextUrl.search;

  const headers = new Headers(request.headers);
  headers.delete('host');
  headers.delete('connection');
  const body = request.method === 'GET' || request.method === 'HEAD' ? undefined : request.body;

  const response = await fetch(target, {
    method: request.method,
    headers,
    body,
    duplex: 'half',
    cache: 'no-store',
  } as RequestInit & { duplex: 'half' });

  const responseHeaders = new Headers(response.headers);
  responseHeaders.delete('content-encoding');
  responseHeaders.delete('content-length');

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: responseHeaders,
  });
}

export const GET = proxy;
export const HEAD = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
