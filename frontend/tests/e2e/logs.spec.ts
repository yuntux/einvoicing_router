import { expect, test } from './fixtures'

test('browses the flow traces, technical logs, and audit logs pages', async ({ page }) => {
  await page.goto('/traces/flow-traces')
  await expect(page.getByRole('heading', { name: 'Traces techniques (API AFNOR)' })).toBeVisible()
  await expect(page.getByTestId('flow-traces-table')).toBeVisible()

  const firstToggle = page.locator('[data-testid^="flow-trace-toggle-"]').first()
  if (await firstToggle.count()) {
    await firstToggle.click()
    await expect(firstToggle).toHaveText('Masquer')
    await firstToggle.click()
    await expect(firstToggle).toHaveText('Détail')
  }

  await page.goto('/traces/technical-logs')
  await expect(page.getByRole('heading', { name: 'Journal des traitements' })).toBeVisible()
  await expect(page.getByTestId('technical-logs-table')).toBeVisible()

  await page.goto('/traces/audit-logs')
  await expect(page.getByRole('heading', { name: "Journal d'audit" })).toBeVisible()
  await expect(page.getByTestId('audit-logs-table')).toBeVisible()
})

test('expands and collapses the "Traces & journaux" nav group', async ({ page }) => {
  await page.goto('/invoices')
  const toggle = page.getByTestId('nav-traces-toggle')
  await toggle.click()
  await expect(page.getByRole('link', { name: 'Traces techniques' })).toBeVisible()
  await page.getByRole('link', { name: 'Traces techniques' }).click()
  await expect(page.getByRole('heading', { name: 'Traces techniques (API AFNOR)' })).toBeVisible()
})
