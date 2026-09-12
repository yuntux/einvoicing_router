import { expect, test } from './fixtures'
import { simulateInvoiceReception, uniqueValidSiren } from './helpers'

test('downloads an invoice file and sees the last download timestamp', async ({ page }) => {
  const unique = uniqueValidSiren()
  const companyName = `Société DL ${unique}`
  const invoiceNumber = `F-${unique}`

  await page.goto('/companies')
  await page.getByTestId('siren-input').fill(unique)
  await page.getByTestId('name-input').fill(companyName)
  await page.getByTestId('submit-button').click()
  await expect(page.getByTestId('companies-list')).toContainText(companyName)

  await simulateInvoiceReception(page, {
    companySiren: unique,
    emitterSiren: unique,
    invoiceNumber,
    invoiceDate: '2026-03-01',
  })

  await page.goto('/invoices')
  await page.getByTestId('filter-invoice-number').fill(invoiceNumber)
  await page.getByTestId('filter-submit-button').click()
  await page.getByTestId(`invoice-row-${invoiceNumber}`).click()

  await expect(page.getByTestId('invoice-last-download')).toContainText('jamais')

  const downloadPromise = page.waitForEvent('download')
  await page.getByTestId('invoice-download-link').click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toContain(invoiceNumber)

  // Re-sélectionne la facture pour récupérer la fiche à jour (jointure AuditLog).
  await page.getByTestId('filter-invoice-number').fill(invoiceNumber)
  await page.getByTestId('filter-submit-button').click()
  await page.getByTestId(`invoice-row-${invoiceNumber}`).click()

  await expect(page.getByTestId('invoice-last-download')).not.toContainText('jamais')
})
