<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { listCompanies, type Company } from '../api/companies'
import {
  createTargetApplication,
  listTargetApplications,
  regenerateTargetApplicationSecret,
  setTargetApplicationActive,
  updateTargetApplication,
  type RoutingMethod,
  type TargetApplication,
  type TargetApplicationCreated,
} from '../api/targetApplications'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import TargetApplicationFormFields, {
  emptyTargetApplicationFieldsState,
  type TargetApplicationFieldsState,
} from '../components/TargetApplicationFormFields.vue'
import { useErrorMessage } from '../composables/useErrorMessage'

const targetApplications = ref<TargetApplication[]>([])
const companies = ref<Company[]>([])
const routingMethod = ref<RoutingMethod>('mail')
const companyId = ref<number | null>(null)
const formState = ref<TargetApplicationFieldsState>(emptyTargetApplicationFieldsState())

const { error, guard } = useErrorMessage()
const createdCredentials = ref<TargetApplicationCreated | null>(null)

// Édition en place des paramètres d'une application existante.
const editingId = ref<number | null>(null)
const edits = reactive<Record<number, TargetApplicationFieldsState>>({})

function companyLabel(companyId: number): string {
  const company = companies.value.find((c) => c.id === companyId)
  return company ? company.name : `#${companyId}`
}

function splitList(value: string): string[] {
  return value
    .split(/[,\n]/)
    .map((v) => v.trim())
    .filter(Boolean)
}

/** Construit `parameters` selon la méthode de routage (§ 4.9.1/4.9.2) — partagé
 * entre création et édition, qui suivent la même logique sur les mêmes champs. */
function buildParameters(method: RoutingMethod, state: TargetApplicationFieldsState) {
  return method === 'mail'
    ? {
        from: state.fromAddress || null,
        to: splitList(state.to),
        cc: splitList(state.cc),
        bcc: splitList(state.bcc),
      }
    : {
        redirect_urls: splitList(state.redirectUrls),
        preferred_conversion_format: state.preferredConversionFormat || null,
        app_type: state.appType,
        webhook_url: state.webhookUrl || null,
      }
}

/** Même règle que le backend (§ `validate_target_application_parameters`,
 * app/schemas/referential.py) — dupliquée ici pour un retour immédiat sans aller-retour
 * serveur, mais le backend reste la source de vérité (jamais fait confiance côté client
 * seul). */
function validateParameters(method: RoutingMethod, parameters: ReturnType<typeof buildParameters>): string | null {
  if (method === 'mail') {
    const { from, to } = parameters as { from: string | null; to: string[] }
    if (!from && to.length === 0) {
      return 'Au moins l\'adresse "De" ou une adresse "À" doit être renseignée.'
    }
  } else {
    const { app_type } = parameters as { app_type: string }
    if (!app_type) {
      return "Le type d'application est obligatoire."
    }
  }
  return null
}

function startEdit(ta: TargetApplication) {
  edits[ta.id] = {
    name: ta.name,
    fromAddress: (ta.parameters.from as string | undefined) ?? '',
    to: ((ta.parameters.to as string[] | undefined) ?? []).join(', '),
    cc: ((ta.parameters.cc as string[] | undefined) ?? []).join(', '),
    bcc: ((ta.parameters.bcc as string[] | undefined) ?? []).join(', '),
    redirectUrls: (ta.oauth_application?.redirect_urls ?? '').split(',').filter(Boolean).join('\n'),
    preferredConversionFormat: ta.oauth_application?.preferred_conversion_format ?? '',
    appType: ta.oauth_application?.app_type ?? 'confidential',
    webhookUrl: ta.oauth_application?.webhook_url ?? '',
  }
  editingId.value = ta.id
}

function cancelEdit() {
  editingId.value = null
}

async function saveEdit(ta: TargetApplication) {
  const parameters = buildParameters(ta.routing_method, edits[ta.id])
  const validationError = validateParameters(ta.routing_method, parameters)
  if (validationError) {
    error.value = validationError
    return
  }
  await guard(async () => {
    await updateTargetApplication(ta.id, { name: edits[ta.id].name, parameters })
    editingId.value = null
    await refresh()
  })
}

async function refresh() {
  targetApplications.value = await listTargetApplications()
}

async function submit() {
  createdCredentials.value = null

  const selectedCompanyId = companyId.value
  if (!selectedCompanyId) {
    error.value = "L'entreprise est requise."
    return
  }

  const parameters = buildParameters(routingMethod.value, formState.value)
  const validationError = validateParameters(routingMethod.value, parameters)
  if (validationError) {
    error.value = validationError
    return
  }

  await guard(async () => {
    const created = await createTargetApplication({
      name: formState.value.name,
      routing_method: routingMethod.value,
      company_id: selectedCompanyId,
      parameters,
    })
    if (created.oauth_client_id && created.oauth_client_secret) {
      createdCredentials.value = created
    }
    formState.value = emptyTargetApplicationFieldsState()
    companyId.value = null
    await refresh()
  })
}

async function toggleActive(ta: TargetApplication) {
  await guard(async () => {
    await setTargetApplicationActive(ta.id, !ta.is_active)
    await refresh()
  })
}

// Renouvellement du secret OAuth (§ afnor_api uniquement) : révoque immédiatement
// l'ancien secret, d'où la confirmation avant d'agir (ConfirmDialog, cohérent avec
// la matrice de Règles de routage) plutôt qu'un clic direct.
const pendingSecretRegen = ref<TargetApplication | null>(null)

function requestRegenerateSecret(ta: TargetApplication) {
  pendingSecretRegen.value = ta
}

function cancelRegenerateSecret() {
  pendingSecretRegen.value = null
}

async function confirmRegenerateSecret() {
  const ta = pendingSecretRegen.value
  if (!ta) return
  pendingSecretRegen.value = null
  createdCredentials.value = null
  await guard(async () => {
    createdCredentials.value = await regenerateTargetApplicationSecret(ta.id)
    await refresh()
  })
}

onMounted(async () => {
  await guard(async () => {
    await refresh()
    companies.value = await listCompanies()
  })
})
</script>

<template>
  <main class="stack">
    <header class="page-header">
      <h1>Applications cibles</h1>
      <p>Canaux vers lesquels les factures peuvent être routées : mail ou API AFNOR.</p>
    </header>

    <section class="card">
      <h2>Ajouter une application cible</h2>
      <form @submit.prevent="submit">
        <div class="field">
          <label for="ta-name-input">Nom</label>
          <input id="ta-name-input" v-model="formState.name" placeholder="Nom" required data-testid="ta-name-input" />
        </div>
        <div class="field">
          <label for="ta-method-select">Méthode de routage</label>
          <select id="ta-method-select" v-model="routingMethod" data-testid="ta-method-select">
            <option value="mail">Routage mail</option>
            <option value="afnor_api">Mise à disposition via API AFNOR</option>
          </select>
        </div>

        <div class="field">
          <label for="ta-company-select">Entreprise</label>
          <select id="ta-company-select" v-model="companyId" required data-testid="ta-company-select">
            <option :value="null" disabled>Entreprise</option>
            <option v-for="company in companies" :key="company.id" :value="company.id">
              {{ company.name }}
            </option>
          </select>
        </div>

        <TargetApplicationFormFields
          v-model="formState"
          :routing-method="routingMethod"
          id-prefix="ta"
          :test-ids="{
            from: 'ta-from-input',
            to: 'ta-to-input',
            cc: 'ta-cc-input',
            bcc: 'ta-bcc-input',
            redirectUrls: 'ta-redirect-urls-input',
            conversionFormat: 'ta-conversion-format-select',
            appType: 'ta-app-type-select',
            webhookUrl: 'ta-webhook-url-input',
          }"
        />

        <button type="submit" data-testid="ta-submit-button">Ajouter</button>
      </form>
    </section>

    <p v-if="error" role="alert">{{ error }}</p>

    <div v-if="createdCredentials" class="card" role="status" data-testid="ta-oauth-credentials">
      <p>
        <strong>Identifiants OAuth — à copier maintenant, le secret ne sera plus
        affiché ensuite.</strong>
      </p>
      <p>Client ID : <code data-testid="ta-oauth-client-id">{{ createdCredentials.oauth_client_id }}</code></p>
      <p>
        Client secret :
        <code data-testid="ta-oauth-client-secret">{{ createdCredentials.oauth_client_secret }}</code>
      </p>
    </div>

    <section class="card">
      <h2>Canaux configurés</h2>
      <table data-testid="target-applications-list">
        <thead>
          <tr>
            <th>Nom</th>
            <th>Méthode de routage</th>
            <th>Entreprise</th>
            <th>Client ID</th>
            <th>Statut</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <template v-for="ta in targetApplications" :key="ta.id">
            <tr :data-testid="`target-application-row-${ta.id}`">
              <td>{{ ta.name }}</td>
              <td><span class="badge badge-info">{{ ta.routing_method }}</span></td>
              <td>{{ companyLabel(ta.company_id) }}</td>
              <td>
                <code v-if="ta.oauth_application" :data-testid="`target-application-client-id-${ta.id}`">
                  {{ ta.oauth_application.client_id }}
                </code>
                <span v-else>—</span>
              </td>
              <td>
                <span class="badge" :class="ta.is_active ? 'badge-success' : 'badge-danger'">
                  {{ ta.is_active ? 'Actif' : 'Inactif' }}
                </span>
              </td>
              <td class="cluster">
                <button
                  type="button"
                  class="btn-secondary btn-sm"
                  :data-testid="`target-application-edit-toggle-${ta.id}`"
                  @click="editingId === ta.id ? cancelEdit() : startEdit(ta)"
                >
                  {{ editingId === ta.id ? 'Annuler' : 'Modifier' }}
                </button>
                <button
                  type="button"
                  class="btn-secondary btn-sm"
                  :data-testid="`target-application-toggle-${ta.id}`"
                  @click="toggleActive(ta)"
                >
                  {{ ta.is_active ? 'Désactiver' : 'Activer' }}
                </button>
                <button
                  v-if="ta.oauth_application"
                  type="button"
                  class="btn-secondary btn-sm"
                  :data-testid="`target-application-regenerate-secret-${ta.id}`"
                  @click="requestRegenerateSecret(ta)"
                >
                  Renouveler le secret OAuth
                </button>
              </td>
            </tr>
            <tr v-if="editingId === ta.id">
              <td colspan="6">
                <form
                  class="stack"
                  :data-testid="`target-application-edit-form-${ta.id}`"
                  @submit.prevent="saveEdit(ta)"
                >
                  <div class="field">
                    <label :for="`ta-edit-name-${ta.id}`">Nom</label>
                    <input
                      :id="`ta-edit-name-${ta.id}`"
                      v-model="edits[ta.id].name"
                      required
                      :data-testid="`target-application-edit-name-${ta.id}`"
                    />
                  </div>

                  <TargetApplicationFormFields
                    v-model="edits[ta.id]"
                    :routing-method="ta.routing_method"
                    :id-prefix="`ta-edit-${ta.id}`"
                    :oauth-client-id="ta.oauth_application?.client_id"
                    :test-ids="{
                      from: `target-application-edit-from-${ta.id}`,
                      to: `target-application-edit-to-${ta.id}`,
                      cc: `target-application-edit-cc-${ta.id}`,
                      bcc: `target-application-edit-bcc-${ta.id}`,
                      redirectUrls: `target-application-edit-redirect-urls-${ta.id}`,
                      conversionFormat: `target-application-edit-conversion-format-${ta.id}`,
                      appType: `target-application-edit-app-type-${ta.id}`,
                      webhookUrl: `target-application-edit-webhook-url-${ta.id}`,
                    }"
                  />

                  <div class="cluster">
                    <button type="submit" class="btn-sm" :data-testid="`target-application-edit-save-${ta.id}`">
                      Enregistrer
                    </button>
                    <button type="button" class="btn-secondary btn-sm" @click="cancelEdit">Annuler</button>
                  </div>
                </form>
              </td>
            </tr>
          </template>
          <tr v-if="targetApplications.length === 0">
            <td colspan="6" class="entity-list-empty">Aucune application cible configurée.</td>
          </tr>
        </tbody>
      </table>
    </section>

    <ConfirmDialog
      :open="pendingSecretRegen !== null"
      title="Renouveler le secret OAuth"
      :message="`Renouveler le secret OAuth de « ${pendingSecretRegen?.name} » ?`"
      detail="L'ancien secret sera immédiatement invalidé — toute intégration qui l'utilise encore cessera de fonctionner tant qu'elle n'aura pas été mise à jour avec le nouveau."
      confirm-label="Renouveler"
      danger
      @confirm="confirmRegenerateSecret"
      @cancel="cancelRegenerateSecret"
    />
  </main>
</template>
