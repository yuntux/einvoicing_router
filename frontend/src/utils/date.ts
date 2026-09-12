const formatter = new Intl.DateTimeFormat('fr-FR', {
  dateStyle: 'short',
  timeStyle: 'medium',
})

const dateOnlyFormatter = new Intl.DateTimeFormat('fr-FR', { dateStyle: 'short' })

/** Formate une date ISO sans heure (`YYYY-MM-DD`) au format français, ex. `12/09/2026`.
 * Construit la date à partir de ses composantes année/mois/jour plutôt que de laisser
 * `Date()` interpréter la chaîne comme un instant UTC : sinon, selon le fuseau du
 * navigateur, minuit UTC peut retomber la veille en heure locale et afficher un jour
 * de moins. */
export function formatDateFr(isoDate: string | null | undefined): string | null {
  if (!isoDate) return null
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(isoDate)
  if (!match) return null
  const [, year, month, day] = match
  const date = new Date(Number(year), Number(month) - 1, Number(day))
  if (Number.isNaN(date.getTime())) return null
  return dateOnlyFormatter.format(date)
}

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
