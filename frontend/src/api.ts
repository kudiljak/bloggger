export const BASE = import.meta.env.VITE_API_URL ?? ''

export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

async function parseError(response: Response): Promise<string> {
  try {
    const data = await response.json()
    if (typeof data?.detail === 'string') return data.detail
    return JSON.stringify(data)
  } catch {
    return response.statusText || 'Request failed'
  }
}

export async function apiJson<T>(
  path: string,
  options: { method?: string; body?: unknown } = {},
): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    method: options.method ?? 'GET',
    credentials: 'include',
    headers: options.body ? { 'Content-Type': 'application/json' } : undefined,
    body: options.body ? JSON.stringify(options.body) : undefined,
  })

  if (!response.ok) {
    throw new ApiError(response.status, await parseError(response))
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export async function apiForm<T>(
  path: string,
  fields: Record<string, string>,
): Promise<T> {
  const body = new URLSearchParams(fields)
  const response = await fetch(`${BASE}${path}`, {
    method: 'POST',
    credentials: 'include',
    body,
  })

  if (!response.ok) {
    throw new ApiError(response.status, await parseError(response))
  }

  return (await response.json()) as T
}
