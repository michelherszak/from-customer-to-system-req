/** Format fetch and upload errors without consuming a response twice. */
export function formatHttpError(body: string, status: number, statusText = ''): string {
  const fallback = `${status} ${statusText}`.trim()
  if (!body.trim()) return fallback
  let detail: unknown
  try {
    const parsed: unknown = JSON.parse(body)
    detail = parsed !== null && typeof parsed === 'object' && 'detail' in parsed ? parsed.detail : parsed
  } catch {
    // Reverse proxies commonly return HTML rather than the API's JSON format.
    return /^\s*(?:<!doctype\s+html|<html\b)/i.test(body) ? fallback : body
  }
  if (detail === null || detail === undefined || detail === '') return fallback
  return typeof detail === 'string' ? detail : JSON.stringify(detail)
}

export async function readHttpError(response: Response): Promise<string> {
  return formatHttpError(await response.text(), response.status, response.statusText)
}
