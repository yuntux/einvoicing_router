<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  createBillingManagerContact,
  deleteBillingManagerContact,
  getRouterSettings,
  listBillingManagerContacts,
  updateRouterSettings,
  type BillingManagerContact,
  type RouterSettings,
} from '../api/settings'
import { useErrorMessage } from '../composables/useErrorMessage'

const settings = ref<RouterSettings | null>(null)
const smtpHost = ref('')
const smtpPort = ref(587)
const smtpUsername = ref('')
const smtpPassword = ref('')
const smtpFromAddress = ref('')
const smtpUseTls = ref(true)
const ihmIpAllowlist = ref('')
const afnorApiIpAllowlist = ref('')

const contacts = ref<BillingManagerContact[]>([])
const newContactEmail = ref('')

const { error, guard } = useErrorMessage()

async function refreshSettings() {
  settings.value = await getRouterSettings()
  smtpHost.value = settings.value.smtp_host ?? ''
  smtpPort.value = settings.value.smtp_port
  smtpUsername.value = settings.value.smtp_username ?? ''
  smtpFromAddress.value = settings.value.smtp_from_address ?? ''
  smtpUseTls.value = settings.value.smtp_use_tls
  ihmIpAllowlist.value = settings.value.ihm_ip_allowlist ?? ''
  afnorApiIpAllowlist.value = settings.value.afnor_api_ip_allowlist ?? ''
}

async function refreshContacts() {
  contacts.value = await listBillingManagerContacts()
}

async function submitSettings() {
  await guard(async () => {
    settings.value = await updateRouterSettings({
      smtp_host: smtpHost.value || null,
      smtp_port: smtpPort.value,
      smtp_username: smtpUsername.value || null,
      smtp_password: smtpPassword.value || null,
      smtp_from_address: smtpFromAddress.value || null,
      smtp_use_tls: smtpUseTls.value,
      ihm_ip_allowlist: ihmIpAllowlist.value || null,
      afnor_api_ip_allowlist: afnorApiIpAllowlist.value || null,
    })
    smtpPassword.value = ''
  })
}

async function submitContact() {
  await guard(async () => {
    await createBillingManagerContact(newContactEmail.value)
    newContactEmail.value = ''
    await refreshContacts()
  })
}

async function removeContact(id: number) {
  await guard(async () => {
    await deleteBillingManagerContact(id)
    await refreshContacts()
  })
}

onMounted(async () => {
  await guard(async () => {
    await refreshSettings()
    await refreshContacts()
  })
})
</script>

<template>
  <main class="stack">
    <header class="page-header">
      <h1>Configuration générale</h1>
      <p>Paramètres transverses du routeur, communs à toutes les entreprises gérées.</p>
    </header>

    <p v-if="error" role="alert">{{ error }}</p>

    <section class="card">
      <h2>Serveur d'envoi SMTP</h2>
      <form @submit.prevent="submitSettings">
        <div class="field">
          <label for="smtp-host-input">Hôte SMTP</label>
          <input id="smtp-host-input" v-model="smtpHost" placeholder="smtp.example.com" data-testid="smtp-host-input" />
        </div>
        <div class="field">
          <label for="smtp-port-input">Port</label>
          <input id="smtp-port-input" v-model.number="smtpPort" type="number" placeholder="Port" data-testid="smtp-port-input" />
        </div>
        <div class="field">
          <label for="smtp-username-input">Identifiant</label>
          <input id="smtp-username-input" v-model="smtpUsername" placeholder="Identifiant" data-testid="smtp-username-input" />
        </div>
        <div class="field">
          <label for="smtp-password-input">Mot de passe</label>
          <input
            id="smtp-password-input"
            v-model="smtpPassword"
            type="password"
            placeholder="Mot de passe"
            data-testid="smtp-password-input"
          />
        </div>
        <div class="field">
          <label for="smtp-from-input">Adresse expéditeur</label>
          <input
            id="smtp-from-input"
            v-model="smtpFromAddress"
            placeholder="Adresse expéditeur"
            data-testid="smtp-from-input"
          />
        </div>
        <label><input v-model="smtpUseTls" type="checkbox" /> TLS</label>
        <button type="submit" data-testid="settings-submit-button">Enregistrer</button>
      </form>
    </section>

    <section class="card">
      <h2>Allowlist IP</h2>
      <p class="card-hint">Adresses ou CIDR IPv4/IPv6 séparés par des virgules. Vide = aucune restriction.</p>
      <form @submit.prevent="submitSettings">
        <div class="field">
          <label for="ihm-ip-allowlist-input">IHM</label>
          <input
            id="ihm-ip-allowlist-input"
            v-model="ihmIpAllowlist"
            placeholder="ex. 203.0.113.0/24, 2001:db8::1"
            data-testid="ihm-ip-allowlist-input"
            style="width: 660px"
          />
        </div>
        <div class="field">
          <label for="afnor-api-ip-allowlist-input">API AFNOR</label>
          <input
            id="afnor-api-ip-allowlist-input"
            v-model="afnorApiIpAllowlist"
            placeholder="ex. 203.0.113.0/24"
            data-testid="afnor-api-ip-allowlist-input"
            style="width: 660px"
          />
        </div>
        <button type="submit" data-testid="ip-allowlist-submit-button">Enregistrer</button>
      </form>
    </section>

    <section class="card">
      <h2>Gestionnaires de facturation</h2>
      <form @submit.prevent="submitContact">
        <input
          v-model="newContactEmail"
          type="email"
          placeholder="Adresse email"
          required
          data-testid="contact-email-input"
        />
        <button type="submit" class="btn-secondary" data-testid="contact-submit-button">Ajouter</button>
      </form>
      <ul class="entity-list" data-testid="billing-manager-contacts-list">
        <li v-if="contacts.length === 0" class="entity-list-empty">Aucun gestionnaire de facturation paramétré.</li>
        <li v-for="contact in contacts" :key="contact.id">
          <span>{{ contact.email }}</span>
          <button type="button" class="btn-danger btn-sm" @click="removeContact(contact.id)">Supprimer</button>
        </li>
      </ul>
    </section>
  </main>
</template>
