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

const error = ref('')

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
  error.value = ''
  try {
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
  } catch (e) {
    error.value = (e as Error).message
  }
}

async function submitContact() {
  error.value = ''
  try {
    await createBillingManagerContact(newContactEmail.value)
    newContactEmail.value = ''
    await refreshContacts()
  } catch (e) {
    error.value = (e as Error).message
  }
}

async function removeContact(id: number) {
  await deleteBillingManagerContact(id)
  await refreshContacts()
}

onMounted(async () => {
  await refreshSettings()
  await refreshContacts()
})
</script>

<template>
  <main>
    <h1>Configuration générale</h1>

    <section>
      <h2>Serveur d'envoi SMTP (§ 4.9.1)</h2>
      <form @submit.prevent="submitSettings">
        <input v-model="smtpHost" placeholder="Hôte SMTP" data-testid="smtp-host-input" />
        <input v-model.number="smtpPort" type="number" placeholder="Port" data-testid="smtp-port-input" />
        <input v-model="smtpUsername" placeholder="Identifiant" data-testid="smtp-username-input" />
        <input
          v-model="smtpPassword"
          type="password"
          placeholder="Mot de passe"
          data-testid="smtp-password-input"
        />
        <input
          v-model="smtpFromAddress"
          placeholder="Adresse expéditeur"
          data-testid="smtp-from-input"
        />
        <label><input v-model="smtpUseTls" type="checkbox" /> TLS</label>
        <button type="submit" data-testid="settings-submit-button">Enregistrer</button>
      </form>
    </section>

    <section>
      <h2>Allowlist IP (§ NF6)</h2>
      <p>Adresses ou CIDR IPv4/IPv6 séparés par des virgules. Vide = aucune restriction.</p>
      <form @submit.prevent="submitSettings">
        <label>
          IHM
          <input
            v-model="ihmIpAllowlist"
            placeholder="ex. 203.0.113.0/24, 2001:db8::1"
            data-testid="ihm-ip-allowlist-input"
          />
        </label>
        <label>
          API AFNOR
          <input
            v-model="afnorApiIpAllowlist"
            placeholder="ex. 203.0.113.0/24"
            data-testid="afnor-api-ip-allowlist-input"
          />
        </label>
        <button type="submit" data-testid="ip-allowlist-submit-button">Enregistrer</button>
      </form>
    </section>

    <section>
      <h2>Gestionnaires de facturation (§ 4.7)</h2>
      <form @submit.prevent="submitContact">
        <input
          v-model="newContactEmail"
          type="email"
          placeholder="Adresse email"
          required
          data-testid="contact-email-input"
        />
        <button type="submit" data-testid="contact-submit-button">Ajouter</button>
      </form>
      <ul data-testid="billing-manager-contacts-list">
        <li v-for="contact in contacts" :key="contact.id">
          {{ contact.email }}
          <button type="button" @click="removeContact(contact.id)">Supprimer</button>
        </li>
      </ul>
    </section>

    <p v-if="error" role="alert">{{ error }}</p>
  </main>
</template>
