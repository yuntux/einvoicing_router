<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { listCompanies, type Company } from '../api/companies'
import {
  createTargetApplication,
  listTargetApplications,
  setTargetApplicationActive,
  updateTargetApplication,
  type RoutingMethod,
  type TargetApplication,
  type TargetApplicationCreated,
} from '../api/targetApplications'
import { useErrorMessage } from '../composables/useErrorMessage'

const targetApplications = ref<TargetApplication[]>([])
const companies = ref<Company[]>([])
const name = ref('')
const routingMethod = ref<RoutingMethod>('mail')
const companyId = ref<number | null>(null)

// Paramètres méthode "mail" (§ 4.9.1)
const to = ref('')
const cc = ref('')
const bcc = ref('')

// Paramètres méthode "afnor_api" (§ 4.9.2)
const redirectUrls = ref('')
const preferredConversionFormat = ref('')
const appType = ref<'confidential' | 'public'>('confidential')
const webhookUrl = ref('')

const { error, guard } = useErrorMessage()
const createdCredentials = ref<TargetApplicationCreated | null>(null)

// Édition en place des paramètres d'une application existante.
const editingId = ref<number | null>(null)
interface EditState {
  name: string
  to: string
  cc: string
  bcc: string
  redirectUrls: string
  preferredConversionFormat: string
  appType: 'confidential' | 'public'
  webhookUrl: string
}
const edits = reactive<Record<number, EditState>>({})

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

function startEdit(ta: TargetApplication) {
  edits[ta.id] = {
    name: ta.name,
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
  const edit = edits[ta.id]
  const parameters =
    ta.routing_method === 'mail'
      ? { to: splitList(edit.to), cc: splitList(edit.cc), bcc: splitList(edit.bcc) }
      : {
          redirect_urls: splitList(edit.redirectUrls),
          preferred_conversion_format: edit.preferredConversionFormat || null,
          app_type: edit.appType,
          webhook_url: edit.webhookUrl || null,
        }
  await guard(async () => {
    await updateTargetApplication(ta.id, { name: edit.name, parameters })
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

  const parameters =
    routingMethod.value === 'mail'
      ? { to: splitList(to.value), cc: splitList(cc.value), bcc: splitList(bcc.value) }
      : {
          redirect_urls: splitList(redirectUrls.value),
          preferred_conversion_format: preferredConversionFormat.value || null,
          app_type: appType.value,
          webhook_url: webhookUrl.value || null,
        }

  await guard(async () => {
    const created = await createTargetApplication({
      name: name.value,
      routing_method: routingMethod.value,
      company_id: selectedCompanyId,
      parameters,
    })
    if (created.oauth_client_id && created.oauth_client_secret) {
      createdCredentials.value = created
    }
    name.value = ''
    companyId.value = null
    to.value = ''
    cc.value = ''
    bcc.value = ''
    redirectUrls.value = ''
    preferredConversionFormat.value = ''
    webhookUrl.value = ''
    await refresh()
  })
}

async function toggleActive(ta: TargetApplication) {
  await guard(async () => {
    await setTargetApplicationActive(ta.id, !ta.is_active)
    await refresh()
  })
}

onMounted(async () => {
  await refresh()
  companies.value = await listCompanies()
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
          <input id="ta-name-input" v-model="name" placeholder="Nom" required data-testid="ta-name-input" />
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

        <div v-if="routingMethod === 'mail'" class="subsection">
          <div class="subsection-title">Destinataires</div>
          <input v-model="to" placeholder="À (séparés par des virgules)" data-testid="ta-to-input" />
          <input v-model="cc" placeholder="CC" data-testid="ta-cc-input" />
          <input v-model="bcc" placeholder="CCI" data-testid="ta-bcc-input" />
        </div>

        <div v-else class="subsection">
          <div class="subsection-title">Application OAuth</div>
          <div class="field">
            <label for="ta-redirect-urls-input">URLs de redirection</label>
            <input
              id="ta-redirect-urls-input"
              v-model="redirectUrls"
              placeholder="URLs de redirection (séparées par des virgules)"
              data-testid="ta-redirect-urls-input"
            />
          </div>
          <div class="field">
            <label for="ta-conversion-format-select">Format préféré de conversion</label>
            <select id="ta-conversion-format-select" v-model="preferredConversionFormat" data-testid="ta-conversion-format-select">
              <option value="">Aucun (facultatif)</option>
              <option value="Factur-X">Factur-X</option>
              <option value="UBL">UBL</option>
              <option value="CII">CII</option>
            </select>
          </div>
          <div class="field">
            <label for="ta-app-type-select">Type d'application</label>
            <select id="ta-app-type-select" v-model="appType" data-testid="ta-app-type-select">
              <option value="confidential">Confidentielle</option>
              <option value="public">Publique</option>
            </select>
          </div>
          <div class="field">
            <label for="ta-webhook-url-input">URL de webhook</label>
            <input
              id="ta-webhook-url-input"
              v-model="webhookUrl"
              placeholder="URL de webhook"
              data-testid="ta-webhook-url-input"
            />
          </div>
        </div>

        <button type="submit" data-testid="ta-submit-button">Ajouter</button>
      </form>
    </section>

    <p v-if="error" role="alert">{{ error }}</p>

    <div v-if="createdCredentials" class="card" role="status" data-testid="ta-oauth-credentials">
      <p>
        <strong>Identifiants OAuth générés — à copier maintenant, le secret ne sera plus
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

                  <div v-if="ta.routing_method === 'mail'" class="subsection">
                    <div class="subsection-title">Destinataires</div>
                    <input
                      v-model="edits[ta.id].to"
                      placeholder="À (séparés par des virgules)"
                      :data-testid="`target-application-edit-to-${ta.id}`"
                    />
                    <input v-model="edits[ta.id].cc" placeholder="CC" />
                    <input v-model="edits[ta.id].bcc" placeholder="CCI" />
                  </div>

                  <div v-else class="subsection">
                    <div class="subsection-title">Application OAuth</div>
                    <div v-if="ta.oauth_application" class="field">
                      <label>Client ID</label>
                      <code :data-testid="`target-application-edit-client-id-${ta.id}`">
                        {{ ta.oauth_application.client_id }}
                      </code>
                    </div>
                    <div class="field">
                      <label :for="`ta-edit-redirect-urls-${ta.id}`">URLs de redirection</label>
                      <textarea
                        :id="`ta-edit-redirect-urls-${ta.id}`"
                        v-model="edits[ta.id].redirectUrls"
                        placeholder="URLs de redirection (une par ligne)"
                        :data-testid="`target-application-edit-redirect-urls-${ta.id}`"
                      />
                    </div>
                    <div class="field">
                      <label :for="`ta-edit-conversion-format-${ta.id}`">Format préféré de conversion</label>
                      <select
                        :id="`ta-edit-conversion-format-${ta.id}`"
                        v-model="edits[ta.id].preferredConversionFormat"
                        :data-testid="`target-application-edit-conversion-format-${ta.id}`"
                      >
                        <option value="">Aucun format préféré (facultatif)</option>
                        <option value="Factur-X">Factur-X</option>
                        <option value="UBL">UBL</option>
                        <option value="CII">CII</option>
                      </select>
                    </div>
                    <div class="field">
                      <label :for="`ta-edit-app-type-${ta.id}`">Type d'application</label>
                      <select
                        :id="`ta-edit-app-type-${ta.id}`"
                        v-model="edits[ta.id].appType"
                        :data-testid="`target-application-edit-app-type-${ta.id}`"
                      >
                        <option value="confidential">Confidentielle</option>
                        <option value="public">Publique</option>
                      </select>
                    </div>
                    <div class="field">
                      <label :for="`ta-edit-webhook-url-${ta.id}`">URL de webhook</label>
                      <input
                        :id="`ta-edit-webhook-url-${ta.id}`"
                        v-model="edits[ta.id].webhookUrl"
                        placeholder="URL de webhook"
                        :data-testid="`target-application-edit-webhook-url-${ta.id}`"
                      />
                    </div>
                  </div>

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
  </main>
</template>
