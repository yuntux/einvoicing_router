export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

interface ApiFetchOptions extends Omit<RequestInit, 'body'> {
  /** Sérialisé en JSON et envoyé comme corps, avec le header Content-Type associé. */
  json?: unknown
}

/** Client HTTP unique pour l'IHM du routeur : centralise `credentials: 'include'`,
 * la sérialisation JSON et la levée d'erreur (message `detail` du backend si présent,
 * sinon `errorLabel: <status>`) pour éviter de répéter ce boilerplate dans chaque
 * fonction de `api/*.ts`. */
export async function apiFetch<T = void>(
  path: string,
  options: ApiFetchOptions = {},
  errorLabel = 'Request failed',
): Promise<T> {
  const { json, ...init } = options
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: 'include',
    ...init,
    ...(json !== undefined && {
      body: JSON.stringify(json),
      headers: { 'Content-Type': 'application/json', ...init.headers },
    }),
  })

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new ApiError(body?.detail ?? `${errorLabel}: ${response.status}`, response.status)
  }
  if (response.status === 204) return undefined as T
  return response.json().catch(() => undefined as T)
}
