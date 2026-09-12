import { expect, test } from './fixtures'
import { simulateInvoiceReception, uniqueValidSiren } from './helpers'

test('simulates an invoice reception and sees it routed', async ({ page }) => {
  const unique = uniqueValidSiren()
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
  const rulesTable = page.getByTestId('routing-rules-list')
  await expect(rulesTable).toContainText(`Fournisseur ${unique}`)
  await expect(rulesTable).toContainText(`Comptable ${unique}`)
  const columnIndex = await rulesTable
    .locator('thead th')
    .evaluateAll((ths, name) => ths.findIndex((th) => th.textContent?.includes(name)), `Comptable ${unique}`)
  const rrow = rulesTable.locator('tbody tr').filter({ hasText: `Fournisseur ${unique}` })
  await rrow.locator('td').nth(columnIndex).locator('input[type="checkbox"]').check()
  await page.getByTestId('confirm-dialog-confirm').click()

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
  await expect(page.getByTestId('lifecycle-events-list')).toContainText('Aucun événement de cycle de vie.')
  await page.getByTestId('invoice-detail-close').click()

  // Filtre par raison sociale émetteur (jointure PartnerDirectory).
  await page.getByTestId('filter-invoice-number').fill('')
  await page.getByTestId('filter-emitter-name').fill(`Fournisseur ${unique}`)
  await page.getByTestId('filter-submit-button').click()
  await expect(page.getByTestId(`invoice-row-${invoiceNumber}`)).toBeVisible()

  // Filtre par montant TTC englobant la facture simulée (1234.56).
  await page.getByTestId('filter-emitter-name').fill('')
  await page.getByTestId('filter-amount-total-min').fill('1000')
  await page.getByTestId('filter-amount-total-max').fill('2000')
  await page.getByTestId('filter-downloaded').selectOption({ label: 'Non' })
  await page.getByTestId('filter-submit-button').click()
  await expect(page.getByTestId(`invoice-row-${invoiceNumber}`)).toBeVisible()

  // Borne de fin antérieure à la borne de début : rejeté côté client, sans appel API.
  await page.getByTestId('filter-amount-total-min').fill('2000')
  await page.getByTestId('filter-amount-total-max').fill('1000')
  await page.getByTestId('filter-submit-button').click()
  await expect(page.getByRole('alert')).toContainText('borne de fin')
})
