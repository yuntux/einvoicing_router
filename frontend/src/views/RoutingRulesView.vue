<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { createPartner, listPartners, type Partner } from '../api/partners'
import { listTargetApplications, type TargetApplication } from '../api/targetApplications'
import { createRoutingRule, listRoutingRules, type RoutingRule } from '../api/routingRules'

const partners = ref<Partner[]>([])
const targetApplications = ref<TargetApplication[]>([])
const rules = ref<RoutingRule[]>([])

// Formulaire "nouvel émetteur"
const newPartnerSiren = ref('')
const newPartnerName = ref('')

// Formulaire "nouvelle règle"
const selectedPartnerId = ref<number | null>(null)
const selectedTargetId = ref<number | null>(null)
const startDate = ref('')
const endDate = ref('')

const error = ref('')

async function refresh() {
  ;[partners.value, targetApplications.value, rules.value] = await Promise.all([
    listPartners(),
    listTargetApplications(),
    listRoutingRules(),
  ])
}

async function submitPartner() {
  error.value = ''
  try {
    await createPartner({ siren: newPartnerSiren.value, name: newPartnerName.value })
    newPartnerSiren.value = ''
    newPartnerName.value = ''
    await refresh()
  } catch (e) {
    error.value = (e as Error).message
  }
}

async function submitRule() {
  error.value = ''
  if (!selectedPartnerId.value || !selectedTargetId.value) {
    error.value = 'Émetteur et application cible requis'
    return
  }
  try {
    await createRoutingRule({
      partner_directory_id: selectedPartnerId.value,
      target_application_id: selectedTargetId.value,
      start_date: startDate.value || null,
      end_date: endDate.value || null,
    })
    startDate.value = ''
    endDate.value = ''
    await refresh()
  } catch (e) {
    error.value = (e as Error).message
  }
}

function partnerLabel(id: number): string {
  const partner = partners.value.find((p) => p.id === id)
  return partner ? `${partner.siren} — ${partner.name}` : String(id)
}

function targetLabel(id: number): string {
  const target = targetApplications.value.find((t) => t.id === id)
  return target ? target.name : String(id)
}

onMounted(refresh)
</script>

<template>
  <main>
    <h1>Règles de routage</h1>

    <section>
      <h2>Émetteurs</h2>
      <form @submit.prevent="submitPartner">
        <input v-model="newPartnerSiren" placeholder="SIREN" maxlength="9" required data-testid="partner-siren-input" />
        <input v-model="newPartnerName" placeholder="Raison sociale" required data-testid="partner-name-input" />
        <button type="submit" data-testid="partner-submit-button">Ajouter un émetteur</button>
      </form>
    </section>

    <section>
      <h2>Nouvelle règle</h2>
      <form @submit.prevent="submitRule">
        <select v-model="selectedPartnerId" data-testid="rule-partner-select">
          <option :value="null" disabled>Émetteur</option>
          <option v-for="p in partners" :key="p.id" :value="p.id">{{ p.siren }} — {{ p.name }}</option>
        </select>
        <select v-model="selectedTargetId" data-testid="rule-target-select">
          <option :value="null" disabled>Application cible</option>
          <option v-for="t in targetApplications" :key="t.id" :value="t.id">{{ t.name }}</option>
        </select>
        <input v-model="startDate" type="date" data-testid="rule-start-date" />
        <input v-model="endDate" type="date" data-testid="rule-end-date" />
        <button type="submit" data-testid="rule-submit-button">Créer la règle</button>
      </form>
    </section>

    <p v-if="error" role="alert">{{ error }}</p>

    <section>
      <h2>Règles existantes</h2>
      <ul data-testid="routing-rules-list">
        <li v-for="rule in rules" :key="rule.id">
          {{ partnerLabel(rule.partner_directory_id) }} → {{ targetLabel(rule.target_application_id) }}
          ({{ rule.start_date ?? '…' }} — {{ rule.end_date ?? '…' }})
        </li>
      </ul>
    </section>
  </main>
</template>
