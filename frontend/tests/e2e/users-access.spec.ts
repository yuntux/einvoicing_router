import { expect, test } from '@playwright/test'

test('manages a user access scope from the users page', async ({ page }) => {
  const unique = String(Date.now()).slice(-9)
  const companyName = `Société Accès ${unique}`

  await page.goto('/companies')
  await page.getByTestId('siren-input').fill(unique)
  await page.getByTestId('name-input').fill(companyName)
  await page.getByTestId('submit-button').click()
  await expect(page.getByTestId('companies-list')).toContainText(companyName)

  // Par défaut (oidc_mode=disabled), la page est accessible sans connexion et ne
  // liste aucun utilisateur tant qu'aucun n'a été provisionné (pas de login réel ici).
  await page.goto('/users')
  await expect(page.getByRole('heading', { name: 'Gestion des accès' })).toBeVisible()
  await expect(page.getByTestId('users-table')).toBeVisible()

  // Pré-provisionnement d'un compte par email (§ NF4) : visible dans la liste avant
  // toute connexion réelle, avec le statut "en attente de première connexion".
  const newEmail = `precree.${unique}@example.com`
  await page.getByTestId('new-user-email-input').fill(newEmail)
  await page.getByTestId('new-user-name-input').fill('Précréé')
  await page.getByTestId('new-user-submit-button').click()
  await expect(page.getByTestId('users-table')).toContainText(newEmail)
  await expect(page.getByTestId('users-table')).toContainText('En attente de première connexion')
})
