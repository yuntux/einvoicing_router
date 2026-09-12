import { expect, test } from '@playwright/test'
import { simulateInvoiceReception } from './helpers'

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
  await page.getByTestId('ta-company-select').selectOption({ label: companyName })
  await page.getByTestId('ta-to-input').fill('compta@example.com')
  await page.getByTestId('ta-submit-button').click()
  await expect(page.getByTestId('target-applications-list')).toContainText(`Comptable ${unique}`)

  await page.goto('/routing-rules')
  await page.getByTestId('partner-siren-input').fill(unique)
  await page.getByTestId('partner-name-input').fill(`Fournisseur ${unique}`)
  await page.getByTestId('partner-submit-button').click()
  const rrow = page
    .locator('[data-testid^="routing-rule-row-"]', { hasText: `Fournisseur ${unique}` })
    .filter({ hasText: `Comptable ${unique}` })
  await expect(rrow).toBeVisible()
  await rrow.locator('input[type="date"]').first().fill('2026-01-01')
  await rrow.getByRole('button', { name: 'Enregistrer' }).click()
  await expect(page.getByTestId('routing-rules-list')).toContainText(`Fournisseur ${unique}`)

  await simulateInvoiceReception(page, {
    companySiren: unique,
    emitterSiren: unique,
    invoiceNumber,
    invoiceDate: '2026-03-01',
  })

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
