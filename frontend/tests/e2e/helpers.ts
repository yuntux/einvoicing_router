import type { Page } from '@playwright/test'

// Backend de test (§ 10.2) — jamais monté en production (cf. app/main.py, actif
// uniquement quand ROUTER_SUPERPDP_CLIENT_MODE=fake, le mode par défaut hors prod).
export const API_BASE = process.env.TEST_API_BASE_URL ?? 'http://localhost:8000'
const TEST_API_BASE = API_BASE

function luhnIsValid(digits: string): boolean {
  let sum = 0
  const reversed = digits.split('').reverse()
  for (let i = 0; i < reversed.length; i++) {
    let digit = Number(reversed[i])
    if (i % 2 === 1) {
      digit *= 2
      if (digit > 9) digit -= 9
    }
    sum += digit
  }
  return sum % 10 === 0
}

/**
 * SIREN unique et valide au sens Luhn (cf. app/schemas/validators.py côté backend) —
 * un `String(Date.now()).slice(-9)` brut est rejeté par l'API une fois sur dix.
 *
 * Régression : dériver uniquement de `Date.now()` (précision milliseconde) produit
 * une VRAIE collision quand deux specs, exécutées dans deux workers Playwright
 * différents, appellent cette fonction à la même milliseconde — plausible au
 * démarrage de la suite, où plusieurs tests appellent ce helper en quelques dizaines
 * de ms les uns des autres. La contrainte `unique` sur `Company.siren` fait alors
 * échouer une des deux créations sans que le test correspondant s'en aperçoive
 * (simplement pas dans la liste ensuite) — symptôme observé en CI sur des tests
 * sans rapport entre eux (entreprises, contacts de facturation, cycle de vie...),
 * chacun créant sa propre entreprise de test. On mélange donc un tirage aléatoire
 * dans le préfixe plutôt que de ne garder que la fin de l'horodatage.
 */
export function uniqueValidSiren(): string {
  const random = Math.floor(Math.random() * 1_000_000)
    .toString()
    .padStart(6, '0')
  const prefix = `${String(Date.now()).slice(-2)}${random}`
  for (let checkDigit = 0; checkDigit <= 9; checkDigit++) {
    const candidate = `${prefix}${checkDigit}`
    if (luhnIsValid(candidate)) return candidate
  }
  throw new Error(`No valid Luhn check digit found for prefix ${prefix}`)
}

/**
 * Injecte une facture reçue via le point d'entrée de test dédié (hors produit,
 * cf. backend/app/api/testing/invoices.py) — remplace l'ancien formulaire de
 * simulation retiré de l'IHM.
 */
export async function simulateInvoiceReception(
  page: Page,
  params: {
    companySiren: string
    emitterSiren: string
    invoiceNumber: string
    invoiceDate: string
    amountTotal?: number
  },
): Promise<void> {
  const companies = await page.request
    .get(`${TEST_API_BASE}/api/ihm/companies`)
    .then((r) => r.json())
  const company = companies.find((c: { siren: string }) => c.siren === params.companySiren)
  if (!company) throw new Error(`Company with siren ${params.companySiren} not found`)

  const response = await page.request.post(`${TEST_API_BASE}/api/test/invoices/simulate`, {
    data: {
      company_id: company.id,
      emitter_siren: params.emitterSiren,
      invoice_number: params.invoiceNumber,
      invoice_date: params.invoiceDate,
      amount_total: params.amountTotal ?? null,
    },
  })
  if (!response.ok()) {
    throw new Error(`Failed to simulate invoice reception: ${response.status()}`)
  }
}
