import { expect, test } from './fixtures'

test('updates general settings and manages billing manager contacts', async ({ page }) => {
  const unique = String(Date.now())
  const contactEmail = `facturation.${unique}@example.com`

  await page.goto('/settings')
  await expect(page.getByRole('heading', { name: 'Configuration générale' })).toBeVisible()

  await page.getByTestId('smtp-host-input').fill('smtp.example.com')
  await page.getByTestId('smtp-port-input').fill('2525')
  await page.getByTestId('smtp-username-input').fill('smtp-user')
  await page.getByTestId('smtp-password-input').fill('smtp-pass')
  await page.getByTestId('smtp-from-input').fill('factures@example.com')
  await page.getByTestId('settings-submit-button').click()

  // Régression : une CIDR qui exclut le runner de test lui-même (ex. `203.0.113.0/24`,
  // qui n'inclut pas `127.0.0.1`) se verrouille immédiatement — `IPAllowlistMiddleware`
  // n'exempte que `/api/ihm/auth/*`, jamais `/api/ihm/settings` lui-même — et pollue
  // `RouterSettings` (une ligne unique, partagée par toute la base de test) pour
  // TOUS les tests suivants de la suite, y compris les étapes suivantes de CE test
  // (création du contact de facturation ci-dessous, elle aussi sous `/api/ihm/*`).
  // On inclut donc explicitement `127.0.0.1/32` en plus de la valeur de démonstration,
  // pour exercer la sauvegarde/persistance du champ sans se bloquer soi-même.
  await page.getByTestId('ihm-ip-allowlist-input').fill('127.0.0.1/32, ::1/128, 203.0.113.0/24')
  await page.getByTestId('afnor-api-ip-allowlist-input').fill('127.0.0.1/32, ::1/128, 198.51.100.0/24')
  await page.getByTestId('ip-allowlist-submit-button').click()

  await page.getByTestId('contact-email-input').fill(contactEmail)
  await page.getByTestId('contact-submit-button').click()
  await expect(page.getByTestId('billing-manager-contacts-list')).toContainText(contactEmail)

  await page
    .getByTestId('billing-manager-contacts-list')
    .locator('li', { hasText: contactEmail })
    .getByRole('button', { name: 'Supprimer' })
    .click()
  await expect(page.getByTestId('billing-manager-contacts-list')).not.toContainText(contactEmail)
})
