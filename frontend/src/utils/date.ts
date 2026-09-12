const formatter = new Intl.DateTimeFormat('fr-FR', {
  dateStyle: 'short',
  timeStyle: 'medium',
})

/** Formate une date ISO (UTC, sans suffixe `Z`) au format français, ex. `12/09/2026 14:32:05`. */
export function formatDateTimeFr(isoDatetime: string | null | undefined): string | null {
  if (!isoDatetime) return null
  // `Date()` ne garantit un parsing fiable des fractions de seconde que sur 3
  // chiffres (millisecondes) — le backend (Python) sérialise en microsecondes
  // (6 chiffres) dès qu'elles sont non nulles, ce que certains navigateurs
  // refusent de parser (Invalid Date) au-delà de 3 décimales.
  let normalized = isoDatetime.replace(/(\.\d{3})\d+/, '$1')
  if (!/Z|[+-]\d\d:\d\d$/.test(normalized)) normalized += 'Z'
  const date = new Date(normalized)
  if (Number.isNaN(date.getTime())) return null
  return formatter.format(date)
}
