// Chaîne vide par défaut = chemin relatif (`/api/...` sur l'origine courante) —
// fonctionne derrière Caddy en prod, quel que soit le domaine. `VITE_API_BASE_URL`
// n'est nécessaire qu'en dev local (cf. .env.development), où le frontend et le
// backend tournent sur des ports séparés sans proxy devant eux.
export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

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

/** `detail` vaut soit une chaîne (`HTTPException(detail="...")`), soit — pour les 422 de
 * validation Pydantic générés automatiquement par FastAPI — une liste d'objets structurés
 * `{msg, loc, type, ...}` : sans ce cas, `new Error(detail)` coerce le tableau en chaîne via
 * `Array.prototype.toString`, qui affiche "[object Object]" au lieu du message de validation. */
// Pydantic préfixe systématiquement "Value error, " au message d'un validateur qui lève une
// simple `ValueError` (§ field_validator, ex. validate_siren) — un détail d'implémentation
// Pydantic sans intérêt pour l'utilisateur, jamais présent pour les autres types d'erreur
// (`missing`, `type_error`...) : on ne le retire donc que lorsqu'il est bien en tête de message.
function stripValueErrorPrefix(msg: string): string {
  return msg.replace(/^Value error,\s*/i, '')
}

function formatErrorDetail(detail: unknown): string | undefined {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item) =>
        item && typeof item === 'object' && 'msg' in item
          ? stripValueErrorPrefix(String((item as { msg: unknown }).msg))
          : String(item),
      )
      .join(' ; ')
  }
  return undefined
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
    throw new ApiError(formatErrorDetail(body?.detail) ?? `${errorLabel}: ${response.status}`, response.status)
  }
  if (response.status === 204) return undefined as T
  return response.json().catch(() => undefined as T)
}
