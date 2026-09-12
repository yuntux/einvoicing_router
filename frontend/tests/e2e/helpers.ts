import type { Page } from '@playwright/test'

// Backend de test (§ 10.2) — jamais monté en production (cf. app/main.py, actif
// uniquement quand ROUTER_SUPERPDP_CLIENT_MODE=fake, le mode par défaut hors prod).
const TEST_API_BASE = process.env.TEST_API_BASE_URL ?? 'http://localhost:8000'

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
