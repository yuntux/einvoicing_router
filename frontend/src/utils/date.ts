const formatter = new Intl.DateTimeFormat('fr-FR', {
  dateStyle: 'short',
  timeStyle: 'medium',
})

/** Formate une date ISO (UTC, sans suffixe `Z`) au format français, ex. `12/09/2026 14:32:05`. */
export function formatDateTimeFr(isoDatetime: string | null | undefined): string | null {
  if (!isoDatetime) return null
  const normalized = /Z|[+-]\d\d:\d\d$/.test(isoDatetime) ? isoDatetime : `${isoDatetime}Z`
  const date = new Date(normalized)
  if (Number.isNaN(date.getTime())) return null
  return formatter.format(date)
}
