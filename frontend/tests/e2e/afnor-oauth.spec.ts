import { expect, test } from './fixtures'
import { API_BASE, uniqueValidSiren } from './helpers'

test('creates an afnor_api target application and reveals OAuth credentials once', async ({
  page,
}) => {
  const unique = uniqueValidSiren()
  const companyName = `Société API ${unique}`

  await page.goto('/companies')
  await page.getByTestId('siren-input').fill(unique)
  await page.getByTestId('name-input').fill(companyName)
  await page.getByTestId('submit-button').click()
  await expect(page.getByTestId('companies-list')).toContainText(companyName)

  await page.goto('/target-applications')
  await page.getByTestId('ta-name-input').fill(`Odoo ${unique}`)
  await page.getByTestId('ta-method-select').selectOption({ value: 'afnor_api' })
  await page.getByTestId('ta-company-select').selectOption({ label: companyName })
  await page.getByTestId('ta-conversion-format-select').selectOption({ label: 'Factur-X' })
  await page.getByTestId('ta-submit-button').click()

  const list = page.getByTestId('target-applications-list')
  await expect(list).toContainText(`Odoo ${unique}`)
  await expect(page.getByTestId('ta-oauth-credentials')).toBeVisible()
  await expect(page.getByTestId('ta-oauth-client-id')).not.toBeEmpty()
  await expect(page.getByTestId('ta-oauth-client-secret')).not.toBeEmpty()

  // Régression : capturer les identifiants AVANT l'édition ci-dessous —
  // `createdCredentials` (§ TargetApplicationsView.vue) est remis à `null` dès
  // l'ouverture du formulaire d'édition ("Modifier"), qui fait disparaître le
  // cartouche "révélé une fois" du DOM ; les lire après aurait renvoyé une chaîne
  // vide et fait échouer la demande de jeton OAuth plus bas.
  const clientId = await page.getByTestId('ta-oauth-client-id').textContent()
  const clientSecret = await page.getByTestId('ta-oauth-client-secret').textContent()

  // Édition des paramètres OAuth d'une application afnor_api existante.
  const taRow = list.locator('tbody tr').filter({ hasText: `Odoo ${unique}` }).first()
  await taRow.getByRole('button', { name: 'Modifier' }).click()
  const editForm = list.locator('[data-testid^="target-application-edit-form-"]')
  await editForm
    .locator('textarea[data-testid^="target-application-edit-redirect-urls-"]')
    .fill('https://odoo.example/callback')
  await editForm.getByRole('button', { name: 'Enregistrer' }).click()
  await expect(editForm).toHaveCount(0)

  // Simule un vrai appel consommateur (Odoo) : authentification OAuth2 puis un
  // appel sur la ressource /flows (émulation de PDP, § 4.4) — de quoi peupler le
  // journal `FlowTrace` (NF1) que la page /traces/flow-traces affiche.
  // Régression : `/oauth/token` est une infrastructure non versionnée (§ 4.10,
  // app/api/afnor/v1.py) montée directement sous `/api/afnor`, sans segment de
  // version — contrairement aux ressources `afnor-flow`/`afnor-directory`
  // ci-dessous, elles bien versionnées. `/api/afnor/v1/oauth/token` n'existe pas
  // (404), d'où l'échec de authentification qui suivait.
  const tokenResponse = await page.request.post(`${API_BASE}/api/afnor/oauth/token`, {
    form: {
      grant_type: 'client_credentials',
      client_id: clientId ?? '',
      client_secret: clientSecret ?? '',
    },
  })
  expect(tokenResponse.ok()).toBeTruthy()
  const { access_token: accessToken } = await tokenResponse.json()

  // Régression : le vrai contrat AFNOR place le numéro de version APRÈS le nom du
  // service (`/afnor-flow/{version}/...`, cf. app/api/afnor/_common.py), jamais
  // comme préfixe global avant le service — `/api/afnor/v1/afnor-flow/...` n'existe
  // pas (404).
  const flowsResponse = await page.request.post(`${API_BASE}/api/afnor/afnor-flow/v1/flows/search`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    data: { where: {} },
  })
  expect(flowsResponse.ok()).toBeTruthy()

  // Note : la consultation d'annuaire (/siren/code-insee:{siren}) exigerait en plus
  // des identifiants SuperPDP configurés pour l'entreprise (§ 4.10) — hors périmètre
  // ici, l'appel ci-dessus suffit à peupler le journal FlowTrace (NF1).
  await page.goto('/traces/flow-traces')
  const traceRow = page.locator('[data-testid^="flow-trace-row-"]').first()
  await expect(traceRow).toBeVisible()
  const toggle = traceRow.locator('[data-testid^="flow-trace-toggle-"]')
  await toggle.click()
  await expect(page.getByText('En-têtes requête')).toBeVisible()
  await expect(toggle).toHaveText('Masquer')
  await toggle.click()
  await expect(toggle).toHaveText('Détail')
})
