const API = import.meta.env.VITE_API_URL ?? '/api/v1'
let csrfToken = sessionStorage.getItem('kusys_csrf') ?? ''

export function setCsrf(token: string) {
  csrfToken = token
  sessionStorage.setItem('kusys_csrf', token)
}

export async function api<T = any>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase()
  const headers = new Headers(init.headers)
  if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && csrfToken) headers.set('X-CSRF-Token', csrfToken)
  const res = await fetch(`${API}${path}`, { ...init, headers, credentials: 'include' })
  if (!res.ok) {
    let detail: any
    try { detail = await res.json() } catch { detail = await res.text() }
    const msg = typeof detail === 'object' ? JSON.stringify(detail.detail ?? detail) : String(detail)
    throw new Error(msg || `${res.status} ${res.statusText}`)
  }
  const contentType = res.headers.get('content-type') ?? ''
  return contentType.includes('application/json') ? res.json() : (res as any)
}

export async function login(username: string, password: string) {
  const data = await api<any>('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) })
  setCsrf(data.csrf_token)
  return data
}

export async function me() {
  const data = await api<any>('/auth/me')
  setCsrf(data.csrf_token)
  return data
}

export function uploadDocument(projectId: string, file: File, onProgress: (percent: number) => void, documentId?: string): Promise<any> {
  const form = new FormData()
  form.append('file', file)
  if (documentId) form.append('document_id', documentId)
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API}/projects/${projectId}/documents`)
    xhr.withCredentials = true
    if (csrfToken) xhr.setRequestHeader('X-CSRF-Token', csrfToken)
    xhr.upload.onprogress = event => {
      if (event.lengthComputable) onProgress(Math.round(event.loaded / event.total * 100))
    }
    xhr.onerror = () => reject(new Error('Upload fehlgeschlagen. Bitte Verbindung prüfen.'))
    xhr.onload = () => {
      let data: any
      try { data = JSON.parse(xhr.responseText) } catch { data = xhr.responseText }
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new Error(typeof data === 'object' ? JSON.stringify(data.detail ?? data) : String(data)))
      } else resolve(data)
    }
    xhr.send(form)
  })
}

export function artifactUrl(id: string) { return `${API}/artifacts/${id}` }
