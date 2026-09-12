import { expect, test } from './fixtures'

test('shows the right message for each login-error reason', async ({ page }) => {
  await page.goto('/login-error?reason=inactive')
  await expect(page.getByTestId('login-error-message')).toContainText('a été désactivé')

  await page.goto('/login-error?reason=conflict')
  await expect(page.getByTestId('login-error-message')).toContainText('déjà utilisée par un autre compte')

  await page.goto('/login-error')
  await expect(page.getByTestId('login-error-message')).toContainText("n'est pré-provisionné")

  await expect(page.getByRole('link', { name: 'Réessayer' })).toBeVisible()
})
