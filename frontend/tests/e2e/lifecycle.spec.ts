import { expect, test } from './fixtures'
import { simulateInvoiceReception, uniqueValidSiren } from './helpers'

test('records a dispute lifecycle event with a reason', async ({ page }) => {
  const unique = uniqueValidSiren()
  const companyName = `Société Cycle ${unique}`
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
    invoiceDate: '2026-04-01',
  })

  await page.goto('/invoices')
  await page.getByTestId('filter-invoice-number').fill(invoiceNumber)
  await page.getByTestId('filter-submit-button').click()
  await page.getByTestId(`invoice-row-${invoiceNumber}`).click()

  // Régression : le titre "Facture <numéro>" est dans l'en-tête de page (fil
  // d'Ariane), en dehors de la section `data-testid="invoice-detail"` elle-même —
  // cf. même correction dans invoices.spec.ts.
  await expect(page.getByRole('heading', { name: `Facture ${invoiceNumber}` })).toBeVisible()

  await page.getByTestId('lifecycle-status-select').selectOption({ label: 'En litige' })
  await page.getByTestId('lifecycle-reason-select').selectOption({ label: 'Taux de TVA erroné' })
  await page.getByTestId('lifecycle-comment-input').fill('Le taux appliqué est incorrect.')
  await page.getByTestId('lifecycle-submit-button').click()

  await expect(page.getByTestId('lifecycle-events-list')).toContainText('dispute')
  await expect(page.getByTestId('lifecycle-events-list')).toContainText('TX_TVA_ERR')
  await expect(page.getByTestId('invoice-detail')).toContainText('dispute')

  // "Refusée" exige en plus la case de confirmation (§ lifecycle_catalog.py).
  await page.getByTestId('lifecycle-status-select').selectOption({ label: 'Refusée' })
  await page.getByTestId('lifecycle-reason-select').selectOption({ label: 'Taux de TVA erroné' })
  await page.getByTestId('lifecycle-confirm-checkbox').check()
  await page.getByTestId('lifecycle-submit-button').click()

  await expect(page.getByTestId('lifecycle-events-list')).toContainText('refused')
})
