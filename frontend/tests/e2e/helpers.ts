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
 * SIREN unique (dérivé de l'horloge, pour ne jamais entrer en collision d'un test
 * à l'autre) et valide au sens Luhn (cf. app/schemas/validators.py côté backend) —
 * un `String(Date.now()).slice(-9)` brut est rejeté par l'API une fois sur dix.
 */
export function uniqueValidSiren(): string {
  const prefix = String(Date.now()).slice(-8)
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
