import { expect, test } from '@playwright/test'

test('creates a mail target application and a routing rule for a new emitter', async ({ page }) => {
  const unique = String(Date.now()).slice(-9)

  await page.goto('/target-applications')
  await expect(page.getByRole('heading', { name: 'Applications cibles' })).toBeVisible()

  await page.getByTestId('ta-name-input').fill(`Spendesk ${unique}`)
  // routing method already defaults to "mail"
  await page.getByTestId('ta-to-input').fill('ap@spendesk.example')
  await page.getByTestId('ta-submit-button').click()
  await expect(page.getByTestId('target-applications-list')).toContainText(`Spendesk ${unique}`)

  await page.goto('/routing-rules')
  await expect(page.getByRole('heading', { name: 'Règles de routage' })).toBeVisible()

  await page.getByTestId('partner-siren-input').fill(unique)
  await page.getByTestId('partner-name-input').fill(`Fournisseur ${unique}`)
  await page.getByTestId('partner-submit-button').click()

  await page.getByTestId('rule-partner-select').selectOption({ label: `${unique} — Fournisseur ${unique}` })
  await page.getByTestId('rule-target-select').selectOption({ label: `Spendesk ${unique}` })
  await page.getByTestId('rule-submit-button').click()

  await expect(page.getByTestId('routing-rules-list')).toContainText(`Fournisseur ${unique}`)
  await expect(page.getByTestId('routing-rules-list')).toContainText(`Spendesk ${unique}`)
})
