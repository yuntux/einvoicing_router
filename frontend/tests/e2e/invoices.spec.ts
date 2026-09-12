import { expect, test } from '@playwright/test'
import { simulateInvoiceReception } from './helpers'

test('simulates an invoice reception and sees it routed', async ({ page }) => {
  const unique = String(Date.now()).slice(-9)
  const companyName = `Société Test ${unique}`
  const emitterSiren = unique
  const invoiceNumber = `F-${unique}`

  // Entreprise réceptrice
  await page.goto('/companies')
  await page.getByTestId('siren-input').fill(unique)
  await page.getByTestId('name-input').fill(companyName)
  await page.getByTestId('submit-button').click()
  await expect(page.getByTestId('companies-list')).toContainText(companyName)

  // Application cible + règle de routage pour l'émetteur
  await page.goto('/target-applications')
  await page.getByTestId('ta-name-input').fill(`Comptable ${unique}`)
  await page.getByTestId('ta-company-select').selectOption({ label: companyName })
  await page.getByTestId('ta-to-input').fill('compta@example.com')
  await page.getByTestId('ta-submit-button').click()
  await expect(page.getByTestId('target-applications-list')).toContainText(`Comptable ${unique}`)

  await page.goto('/routing-rules')
  await page.getByTestId('partner-siren-input').fill(emitterSiren)
  await page.getByTestId('partner-name-input').fill(`Fournisseur ${unique}`)
  await page.getByTestId('partner-submit-button').click()
  const rrow = page
    .locator('[data-testid^="routing-rule-row-"]', { hasText: `Fournisseur ${unique}` })
    .filter({ hasText: `Comptable ${unique}` })
  await expect(rrow).toBeVisible()
  await rrow.getByRole('button', { name: 'Enregistrer' }).click()
  await expect(page.getByTestId('routing-rules-list')).toContainText(`Fournisseur ${unique}`)

  // Injection d'une facture reçue de cet émetteur (point d'entrée de test, § 10.2)
  await simulateInvoiceReception(page, {
    companySiren: unique,
    emitterSiren,
    invoiceNumber,
    invoiceDate: '2026-03-01',
    amountTotal: 1234.56,
  })

  await page.goto('/invoices')
  await page.getByTestId('filter-invoice-number').fill(invoiceNumber)
  await page.getByTestId('filter-submit-button').click()

  const row = page.getByTestId(`invoice-row-${invoiceNumber}`)
  await expect(row).toBeVisible()
  await row.click()

  await expect(page.getByTestId('invoice-detail')).toContainText(invoiceNumber)
  await expect(page.getByTestId('invoice-routings-list')).toContainText('to_send')
})
