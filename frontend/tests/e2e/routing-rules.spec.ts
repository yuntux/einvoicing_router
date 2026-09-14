import { expect, test } from './fixtures'
import { simulateInvoiceReception, uniqueValidSiren } from './helpers'

test('creates a mail target application and a routing rule for a new emitter', async ({ page }) => {
  const unique = uniqueValidSiren()
  const companyName = `Société Routage ${unique}`

  await page.goto('/companies')
  await page.getByTestId('siren-input').fill(unique)
  await page.getByTestId('name-input').fill(companyName)
  await page.getByTestId('submit-button').click()
  await expect(page.getByTestId('companies-list')).toContainText(companyName)

  await page.goto('/target-applications')
  await expect(page.getByRole('heading', { name: 'Applications cibles' })).toBeVisible()

  await page.getByTestId('ta-name-input').fill(`Spendesk ${unique}`)
  // routing method already defaults to "mail"
  await page.getByTestId('ta-company-select').selectOption({ label: companyName })
  await page.getByTestId('ta-to-input').fill('ap@spendesk.example')
  await page.getByTestId('ta-submit-button').click()
  await expect(page.getByTestId('target-applications-list')).toContainText(`Spendesk ${unique}`)

  await page.goto('/routing-rules')
  await expect(page.getByRole('heading', { level: 1, name: 'Règles de routage' })).toBeVisible()

  await page.getByTestId('partner-siren-input').fill(unique)
  await page.getByTestId('partner-name-input').fill(`Fournisseur ${unique}`)
  await page.getByTestId('partner-submit-button').click()

  const table = page.getByTestId('routing-rules-list')
  await expect(table).toContainText(`Fournisseur ${unique}`)
  await expect(table).toContainText(`Spendesk ${unique}`)

  const columnIndex = await table
    .locator('thead th')
    .evaluateAll((ths, name) => ths.findIndex((th) => th.textContent?.includes(name)), `Spendesk ${unique}`)
  const row = table.locator('tbody tr').filter({ hasText: `Fournisseur ${unique}` })
  const checkbox = row.locator('td').nth(columnIndex).locator('input[type="checkbox"]')
  await checkbox.check()
  await page.getByTestId('confirm-dialog-confirm').click()
  await expect(checkbox).toBeChecked()

  // Annuler la désactivation restaure l'état visuel de la case (elle reste cochée).
  await checkbox.uncheck()
  await page.getByTestId('confirm-dialog-cancel').click()
  await expect(checkbox).toBeChecked()
})

test('activating a 2nd channel offers to reroute existing invoices or not', async ({ page }) => {
  const unique = uniqueValidSiren()
  const companyName = `Société Multi-canal ${unique}`
  const emitterSiren = unique
  const invoiceNumber = `F-${unique}`

  await page.goto('/companies')
  await page.getByTestId('siren-input').fill(unique)
  await page.getByTestId('name-input').fill(companyName)
  await page.getByTestId('submit-button').click()
  await expect(page.getByTestId('companies-list')).toContainText(companyName)

  // Deux applications cibles (canal A et canal B) pour la même entreprise.
  await page.goto('/target-applications')
  await page.getByTestId('ta-name-input').fill(`Canal A ${unique}`)
  await page.getByTestId('ta-company-select').selectOption({ label: companyName })
  await page.getByTestId('ta-to-input').fill('a@example.com')
  await page.getByTestId('ta-submit-button').click()
  await expect(page.getByTestId('target-applications-list')).toContainText(`Canal A ${unique}`)

  await page.getByTestId('ta-name-input').fill(`Canal B ${unique}`)
  await page.getByTestId('ta-company-select').selectOption({ label: companyName })
  await page.getByTestId('ta-to-input').fill('b@example.com')
  await page.getByTestId('ta-submit-button').click()
  await expect(page.getByTestId('target-applications-list')).toContainText(`Canal B ${unique}`)

  // Fournisseur routé uniquement vers le canal A pour l'instant.
  await page.goto('/routing-rules')
  await page.getByTestId('partner-siren-input').fill(emitterSiren)
  await page.getByTestId('partner-name-input').fill(`Fournisseur ${unique}`)
  await page.getByTestId('partner-submit-button').click()

  const rulesTable = page.getByTestId('routing-rules-list')
  await expect(rulesTable).toContainText(`Canal A ${unique}`)
  await expect(rulesTable).toContainText(`Canal B ${unique}`)

  const columnIndexFor = (name: string) =>
    rulesTable
      .locator('thead th')
      .evaluateAll((ths, n) => ths.findIndex((th) => th.textContent?.includes(n)), name)

  const row = rulesTable.locator('tbody tr').filter({ hasText: `Fournisseur ${unique}` })
  const columnA = await columnIndexFor(`Canal A ${unique}`)
  const columnB = await columnIndexFor(`Canal B ${unique}`)
  const checkboxA = row.locator('td').nth(columnA).locator('input[type="checkbox"]')
  const checkboxB = row.locator('td').nth(columnB).locator('input[type="checkbox"]')

  await checkboxA.check()
  // La popin d'activation du 1er canal du fournisseur propose bien les 2 options.
  await expect(page.getByTestId('reroute-choice')).toBeVisible()
  await page.getByTestId('confirm-dialog-confirm').click()

  // Facture déjà reçue de ce fournisseur, routée au fil de l'eau vers le canal A.
  await simulateInvoiceReception(page, {
    companySiren: unique,
    emitterSiren,
    invoiceNumber,
    invoiceDate: '2026-03-01',
  })

  // Régression : `invoice-routings-list` est un `<table>` (`tbody > tr`), plus une
  // `<ul><li>` — depuis la conversion popin -> page routée du détail facture.
  await page.goto('/invoices')
  await page.getByTestId('filter-invoice-number').fill(invoiceNumber)
  await page.getByTestId('filter-submit-button').click()
  await page.getByTestId(`invoice-row-${invoiceNumber}`).click()
  await expect(page.getByTestId('invoice-routings-list').locator('tbody tr')).toHaveCount(1)

  // Active le canal B en choisissant "futures uniquement" : la facture déjà reçue
  // ne doit PAS être routée vers B en plus de A.
  await page.goto('/routing-rules')
  await checkboxB.check()
  await page.getByTestId('reroute-choice-future-only').check()
  await page.getByTestId('confirm-dialog-confirm').click()

  await page.goto('/invoices')
  await page.getByTestId('filter-invoice-number').fill(invoiceNumber)
  await page.getByTestId('filter-submit-button').click()
  await page.getByTestId(`invoice-row-${invoiceNumber}`).click()
  await expect(page.getByTestId('invoice-routings-list').locator('tbody tr')).toHaveCount(1)

  // Désactive puis réactive le canal B, cette fois avec le choix par défaut
  // ("toutes les factures déjà reçues") : la facture doit alors recevoir un 2e
  // routage vers B, sans dupliquer celui déjà en place vers A.
  await page.goto('/routing-rules')
  await checkboxB.uncheck()
  await page.getByTestId('confirm-dialog-confirm').click()
  await checkboxB.check()
  await expect(page.getByTestId('reroute-choice-existing')).toBeChecked()
  await page.getByTestId('confirm-dialog-confirm').click()

  await page.goto('/invoices')
  await page.getByTestId('filter-invoice-number').fill(invoiceNumber)
  await page.getByTestId('filter-submit-button').click()
  await page.getByTestId(`invoice-row-${invoiceNumber}`).click()
  await expect(page.getByTestId('invoice-routings-list').locator('tbody tr')).toHaveCount(2)
})

test('edits a mail target application and toggles it inactive then active', async ({ page }) => {
  const unique = uniqueValidSiren()
  const companyName = `Société Édition ${unique}`

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
  const list = page.getByTestId('target-applications-list')
  await expect(list).toContainText(`Comptable ${unique}`)

  const taRow = list.locator('tbody tr').filter({ hasText: `Comptable ${unique}` }).first()
  await taRow.getByRole('button', { name: 'Modifier' }).click()

  const editForm = list.locator('[data-testid^="target-application-edit-form-"]')
  await editForm.locator('input[data-testid^="target-application-edit-name-"]').fill(`Comptable ${unique} v2`)
  await editForm.locator('input[data-testid^="target-application-edit-to-"]').fill('nouveau@example.com')
  await editForm.getByRole('button', { name: 'Enregistrer' }).click()
  await expect(list).toContainText(`Comptable ${unique} v2`)

  // Réouvre l'édition : le champ "to" reflète bien la nouvelle valeur enregistrée.
  await taRow.getByRole('button', { name: 'Modifier' }).click()
  await expect(editForm.locator('input[data-testid^="target-application-edit-to-"]')).toHaveValue(
    'nouveau@example.com',
  )
  await editForm.getByRole('button', { name: 'Annuler' }).click()

  await taRow.getByRole('button', { name: 'Désactiver' }).click()
  await expect(taRow).toContainText('Inactif')
  await taRow.getByRole('button', { name: 'Activer' }).click()
  await expect(taRow).toContainText('Actif')
})
