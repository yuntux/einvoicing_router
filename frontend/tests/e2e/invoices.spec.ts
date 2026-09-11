import { expect, test } from '@playwright/test'

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
  await page.getByTestId('ta-to-input').fill('compta@example.com')
  await page.getByTestId('ta-submit-button').click()
  await expect(page.getByTestId('target-applications-list')).toContainText(`Comptable ${unique}`)

  await page.goto('/routing-rules')
  await page.getByTestId('partner-siren-input').fill(emitterSiren)
  await page.getByTestId('partner-name-input').fill(`Fournisseur ${unique}`)
  await page.getByTestId('partner-submit-button').click()
  await page.getByTestId('rule-partner-select').selectOption({ label: `${emitterSiren} — Fournisseur ${unique}` })
  await page.getByTestId('rule-target-select').selectOption({ label: `Comptable ${unique}` })
  await page.getByTestId('rule-submit-button').click()
  await expect(page.getByTestId('routing-rules-list')).toContainText(`Fournisseur ${unique}`)

  // Simulation de réception d'une facture de cet émetteur
  await page.goto('/invoices')
  await page.getByTestId('sim-company-select').selectOption({ label: `${unique} — ${companyName}` })
  await page.getByTestId('sim-emitter-siren-input').fill(emitterSiren)
  await page.getByTestId('sim-invoice-number-input').fill(invoiceNumber)
  await page.getByTestId('sim-invoice-date-input').fill('2026-03-01')
  await page.getByTestId('sim-amount-input').fill('1234.56')
  await page.getByTestId('sim-submit-button').click()

  await page.getByTestId('filter-invoice-number').fill(invoiceNumber)
  await page.getByTestId('filter-submit-button').click()

  const row = page.getByTestId(`invoice-row-${invoiceNumber}`)
  await expect(row).toBeVisible()
  await row.click()

  await expect(page.getByTestId('invoice-detail')).toContainText(invoiceNumber)
  await expect(page.getByTestId('invoice-routings-list')).toContainText('to_send')
})
