import { expect, test } from '@playwright/test'

test('records a dispute lifecycle event with a reason', async ({ page }) => {
  const unique = String(Date.now()).slice(-9)
  const companyName = `Société Cycle ${unique}`
  const invoiceNumber = `F-${unique}`

  await page.goto('/companies')
  await page.getByTestId('siren-input').fill(unique)
  await page.getByTestId('name-input').fill(companyName)
  await page.getByTestId('submit-button').click()
  await expect(page.getByTestId('companies-list')).toContainText(companyName)

  await page.goto('/invoices')
  await page.getByTestId('sim-company-select').selectOption({ label: `${unique} — ${companyName}` })
  await page.getByTestId('sim-emitter-siren-input').fill(unique)
  await page.getByTestId('sim-invoice-number-input').fill(invoiceNumber)
  await page.getByTestId('sim-invoice-date-input').fill('2026-04-01')
  await page.getByTestId('sim-submit-button').click()

  await page.getByTestId('filter-invoice-number').fill(invoiceNumber)
  await page.getByTestId('filter-submit-button').click()
  await page.getByTestId(`invoice-row-${invoiceNumber}`).click()

  await expect(page.getByTestId('invoice-detail')).toContainText(invoiceNumber)

  await page.getByTestId('lifecycle-status-select').selectOption({ label: 'En litige' })
  await page.getByTestId('lifecycle-reason-select').selectOption({ label: 'Taux de TVA erroné' })
  await page.getByTestId('lifecycle-comment-input').fill('Le taux appliqué est incorrect.')
  await page.getByTestId('lifecycle-submit-button').click()

  await expect(page.getByTestId('lifecycle-events-list')).toContainText('dispute')
  await expect(page.getByTestId('lifecycle-events-list')).toContainText('TX_TVA_ERR')
  await expect(page.getByTestId('invoice-detail')).toContainText('dispute')
})
