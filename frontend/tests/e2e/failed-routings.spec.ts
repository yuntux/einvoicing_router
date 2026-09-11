import { expect, test } from '@playwright/test'

test('forces a send cycle, sees a failed routing, and replays it manually', async ({ page }) => {
  const unique = String(Date.now()).slice(-9)
  const companyName = `Société Retry ${unique}`
  const invoiceNumber = `F-${unique}`

  await page.goto('/companies')
  await page.getByTestId('siren-input').fill(unique)
  await page.getByTestId('name-input').fill(companyName)
  await page.getByTestId('submit-button').click()
  await expect(page.getByTestId('companies-list')).toContainText(companyName)

  await page.goto('/target-applications')
  await page.getByTestId('ta-name-input').fill(`Comptable ${unique}`)
  await page.getByTestId('ta-to-input').fill('compta@example.com')
  await page.getByTestId('ta-submit-button').click()
  await expect(page.getByTestId('target-applications-list')).toContainText(`Comptable ${unique}`)

  await page.goto('/routing-rules')
  await page.getByTestId('partner-siren-input').fill(unique)
  await page.getByTestId('partner-name-input').fill(`Fournisseur ${unique}`)
  await page.getByTestId('partner-submit-button').click()
  await page.getByTestId('rule-partner-select').selectOption({ label: `${unique} — Fournisseur ${unique}` })
  await page.getByTestId('rule-target-select').selectOption({ label: `Comptable ${unique}` })
  await page.getByTestId('rule-submit-button').click()
  await expect(page.getByTestId('routing-rules-list')).toContainText(`Fournisseur ${unique}`)

  await page.goto('/invoices')
  await page.getByTestId('sim-company-select').selectOption({ label: `${unique} — ${companyName}` })
  await page.getByTestId('sim-emitter-siren-input').fill(unique)
  await page.getByTestId('sim-invoice-number-input').fill(invoiceNumber)
  await page.getByTestId('sim-invoice-date-input').fill('2026-03-01')
  await page.getByTestId('sim-submit-button').click()

  // Aucun serveur SMTP réel n'est configuré : forcer le cycle d'envoi fait échouer la
  // tentative et bascule l'InvoiceRouting en retry (§ 4.7).
  await page.goto('/failed-routings')
  await page.getByTestId('force-send-cycle-button').click()

  const row = page.locator('[data-testid^="failed-routing-row-"]', { hasText: invoiceNumber })
  await expect(row).toBeVisible()
  await expect(row).toContainText('retrying')

  const checkbox = row.locator('input[type="checkbox"]')
  await checkbox.check()
  await page.getByTestId('replay-selected-button').click()

  await expect(page.getByRole('status')).toContainText('rejeu')

  // Rejeu manuel = essai unique (§ 4.7) : sans SMTP réel, il retombe en échec définitif.
  const rowAfterReplay = page.locator('[data-testid^="failed-routing-row-"]', {
    hasText: invoiceNumber,
  })
  await expect(rowAfterReplay).toContainText('failed_final')
})
