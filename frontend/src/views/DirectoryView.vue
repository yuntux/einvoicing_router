<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  checkPeppolStatus,
  listDirectoryLines,
  searchDirectory,
  type DirectoryEntity,
  type DirectoryLine,
  type DirectoryLineAddress,
  type DirectoryLinePeppolStatus,
  type DirectoryResource,
} from '../api/directory'
import { listCompanyLookups, type CompanyLookup } from '../api/companies'
import { useErrorMessage } from '../composables/useErrorMessage'

const route = useRoute()
const router = useRouter()
const { error, guard } = useErrorMessage()

const companies = ref<CompanyLookup[]>([])
// § "mise par défaut sur sa première entrée" — pas de valeur vide dans le
// sélecteur : la recherche est toujours faite avec les identifiants d'une
// entreprise précise, jamais "toutes les entreprises" (l'annuaire SuperPDP n'a pas
// cette notion, chaque appel est scopé à une seule entreprise gérée, § 4.10).
const companyId = ref<number | null>(null)

const resource = ref<DirectoryResource>('siren')

// Champs de recherche par type — non pertinents pour les autres types (§
// DirectorySearchRequest.build_body côté backend, qui ignore ceux hors du type
// choisi).
const searchSiren = ref('')
const searchBusinessName = ref('')
const searchSiret = ref('')
const searchName = ref('')
const searchPostalCode = ref('')
const searchLocality = ref('')
const searchRoutingIdentifier = ref('')
const searchRoutingCodeName = ref('')
const searchRoutingSiret = ref('')

const results = ref<DirectoryEntity[]>([])
const totalResults = ref(0)
const searched = ref(false)

async function runSearch() {
  if (!companyId.value) return
  peppolCheckResult.value = null
  await guard(async () => {
    const params =
      resource.value === 'siren'
        ? { company_id: companyId.value!, resource: resource.value, siren: searchSiren.value || undefined, business_name: searchBusinessName.value || undefined }
        : resource.value === 'siret'
          ? {
              company_id: companyId.value!,
              resource: resource.value,
              siret: searchSiret.value || undefined,
              name: searchName.value || undefined,
              postal_code: searchPostalCode.value || undefined,
              locality: searchLocality.value || undefined,
            }
          : {
              company_id: companyId.value!,
              resource: resource.value,
              routing_identifier: searchRoutingIdentifier.value || undefined,
              routing_code_name: searchRoutingCodeName.value || undefined,
              siret: searchRoutingSiret.value || undefined,
            }
    const data = await searchDirectory(params)
    results.value = data.results
    totalResults.value = data.totalNumberOfResults
    searched.value = true
  })
}

// Identifiant utilisable pour une vérification Peppol directe (§ bouton "Rechercher
// sur l'annuaire Peppol") — celui actuellement saisi dans le champ pertinent du mode
// de recherche actif. Peppol n'a pas de recherche par nom : `business_name`/`name`/
// `routing_code_name` ne sont jamais utilisables ici.
const peppolIdentifier = computed(() => {
  if (resource.value === 'siren') return searchSiren.value.trim()
  if (resource.value === 'siret') return searchSiret.value.trim()
  return (searchRoutingIdentifier.value || searchRoutingSiret.value).trim()
})

const peppolCheckResult = ref<DirectoryLinePeppolStatus | null>(null)
const peppolCheckIdentifier = ref('')

async function runPeppolCheck() {
  const identifier = peppolIdentifier.value
  if (!identifier) {
    error.value = 'Un SIREN, SIRET ou identifiant de routage est requis pour la vérification Peppol.'
    return
  }
  searched.value = false
  await guard(async () => {
    peppolCheckResult.value = await checkPeppolStatus(identifier)
    peppolCheckIdentifier.value = identifier
  })
}

watch(resource, () => {
  peppolCheckResult.value = null
})

const showDirectoryScopeHelp = ref(false)

function entitySiren(entity: DirectoryEntity): string | undefined {
  return entity.siren ?? entity.legalUnit?.siren
}

function entitySiret(entity: DirectoryEntity): string | undefined {
  return entity.siret ?? entity.facility?.siret
}

function openEntity(entity: DirectoryEntity) {
  router.push({
    name: 'directory',
    query: {
      company: String(companyId.value),
      resource: resource.value,
      ...(entitySiren(entity) ? { siren: entitySiren(entity) } : {}),
      ...(entitySiret(entity) ? { siret: entitySiret(entity) } : {}),
      ...(entity.routingIdentifier ? { routing_identifier: entity.routingIdentifier } : {}),
    },
  })
}

function goBackToSearch() {
  router.push({ name: 'directory' })
}

// Meilleur libellé lisible disponible pour une ligne d'annuaire — aucun champ de la
// ligne elle-même n'en porte un directement (seulement des identifiants bruts),
// d'où la dépendance à `legalUnit`/`facility` (§ `include` étendu côté backend).
function lineLabel(line: DirectoryLine): string {
  return line.facility?.name ?? line.legalUnit?.businessName ?? line.routingCode?.routingCodeName ?? '—'
}

const PLATFORM_TYPE_LABEL: Record<string, string> = {
  WK: 'Plateforme partenaire (PA)',
  DFH: 'Portail public de facturation (Chorus Pro)',
}

function platformTypeLabel(line: DirectoryLine): string {
  return (line.platformType && PLATFORM_TYPE_LABEL[line.platformType]) ?? '—'
}

function formatAddress(address: DirectoryLineAddress | undefined): string | null {
  if (!address) return null
  const lines = [address.addressLine1, address.addressLine2, address.addressLine3].filter(Boolean)
  const locality = [address.postalCode, address.locality, address.countrySubdivision].filter(Boolean).join(' ')
  const country = address.countryName ?? address.countryCode
  return [...lines, [locality, country].filter(Boolean).join(' — ')].filter(Boolean).join(', ')
}

function yesNo(value: boolean | undefined): string {
  if (value === undefined) return '—'
  return value ? 'Oui' : 'Non'
}

// Statut administratif [A - Active, C - Closed] — même énumération à deux valeurs
// pour `legalUnit`/`facility`/`routingCode.administrativeStatus` (§ contrat AFNOR).
const ADMIN_STATUS_LABEL: Record<string, string> = { A: 'Actif', C: 'Fermé' }

function adminStatusLabel(status: string | undefined): string {
  return (status && ADMIN_STATUS_LABEL[status]) ?? status ?? '—'
}

function openLine(line: DirectoryLine) {
  router.push({ name: 'directory', query: { ...route.query, line: line.addressingIdentifier } })
}

function goBackToEntity() {
  const query = { ...route.query }
  delete query.line
  router.push({ name: 'directory', query })
}

const selectedLineIdentifier = computed(() => (route.query.line as string) || undefined)
const selectedLine = computed(
  () => directoryLines.value.find((l) => l.addressingIdentifier === selectedLineIdentifier.value) ?? null,
)

// Mode détail : présent dès que l'URL porte un `resource` + un identifiant — sinon
// c'est le formulaire de recherche qui est affiché (§ "comme pour les factures").
const detailQuery = computed(() => {
  const q = route.query
  if (!q.resource || !q.company) return null
  return {
    companyId: Number(q.company),
    resource: q.resource as DirectoryResource,
    siren: (q.siren as string) || undefined,
    siret: (q.siret as string) || undefined,
    routingIdentifier: (q.routing_identifier as string) || undefined,
  }
})

const detailEntity = ref<DirectoryEntity | null>(null)
const directoryLines = ref<DirectoryLine[]>([])
const directoryLinesLoading = ref(false)
const directoryLinesError = ref('')

async function loadDetail() {
  const q = detailQuery.value
  if (!q) {
    detailEntity.value = null
    directoryLines.value = []
    directoryLinesError.value = ''
    return
  }
  const searchParams =
    q.resource === 'siren'
      ? { company_id: q.companyId, resource: q.resource, siren: q.siren }
      : q.resource === 'siret'
        ? { company_id: q.companyId, resource: q.resource, siret: q.siret }
        : { company_id: q.companyId, resource: q.resource, routing_identifier: q.routingIdentifier, siret: q.siret }

  // Deux appels indépendants (§ bug page blanche/erreur constaté sur un SIREN à
  // très nombreuses lignes d'annuaire, ex. "Services de l'État") : la recherche de
  // l'entité elle-même est rapide et ne doit jamais rester bloquée par la
  // récupération des lignes d'annuaire, plus lente (résolution Peppol par ligne
  // côté backend, § `list_directory_lines`) et plus susceptible d'expirer.
  directoryLines.value = []
  directoryLinesError.value = ''
  directoryLinesLoading.value = true
  const linesPromise = listDirectoryLines({ company_id: q.companyId, siren: q.siren, siret: q.siret })
    .then((linesData) => {
      directoryLines.value = linesData.results
    })
    .catch((err) => {
      directoryLinesError.value = err instanceof Error ? err.message : 'Failed to list directory lines'
    })
    .finally(() => {
      directoryLinesLoading.value = false
    })

  await guard(async () => {
    const searchData = await searchDirectory(searchParams)
    detailEntity.value = searchData.results[0] ?? null
  })

  await linesPromise
}

watch(() => route.query, loadDetail)

onMounted(async () => {
  await guard(async () => {
    companies.value = await listCompanyLookups({ certifiedPlatformConfigured: true })
    if (companies.value.length) companyId.value = companies.value[0].id
  })
  await loadDetail()
})
</script>

<template>
  <main class="stack">
    <p v-if="error" role="alert">{{ error }}</p>

    <template v-if="!detailQuery">
      <header class="page-header">
        <h1>Annuaires</h1>
        <p>Recherche dans l'annuaire DGFIP (via l'API normalisée AFNOR exposée par la plateforme agréée) et dans l'annuaire Peppol (via une requete DNS NAPTR sur le SLM du réseau Peppol).</p>
      </header>

      <section class="card">
        <h2 style="position: relative; display: inline-flex; align-items: center">
          Recherche
          <button
            type="button"
            class="legend-help-button"
            aria-label="Différence entre annuaire DGFIP et annuaire Peppol"
            data-testid="directory-scope-help-toggle"
            @click="showDirectoryScopeHelp = !showDirectoryScopeHelp"
          >
            ?
          </button>
          <div
            v-if="showDirectoryScopeHelp"
            class="legend-popover"
            style="min-width: 480px; right: auto; left: 0"
            data-testid="directory-scope-help-popover"
          >
            <button
              type="button"
              class="legend-popover-close"
              aria-label="Fermer"
              @click="showDirectoryScopeHelp = false"
            >
              ×
            </button>
            <p style="margin: 0 0 8px">
              <strong>Annuaire DGFIP</strong> : périmètre de la réforme française — les
              assujettis à la TVA en France, y compris ceux en franchise en base.
            </p>
            <p style="margin: 0 0 10px">
              <strong>Annuaire Peppol</strong> : annuaire international, indépendant de
              la réforme française.
            </p>
            <table>
              <thead>
                <tr>
                  <th>Population</th>
                  <th>Annuaire DGFIP</th>
                  <th>Annuaire Peppol</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Entreprises de la réforme FR</td>
                  <td>✓</td>
                  <td>✓</td>
                </tr>
                <tr>
                  <td>Services publics de la réforme FR</td>
                  <td>✓</td>
                  <td>✗ (Chorus Pro non connectée au réseau Peppol)</td>
                </tr>
                <tr>
                  <td>Entités hors réforme FR, joignables via Peppol</td>
                  <td>✗</td>
                  <td>✓</td>
                </tr>
              </tbody>
            </table>
            <p class="entity-sub" style="margin: 8px 0 0">
              Pour cette dernière catégorie : un e-reporting à la DGFIP reste dû à
              l'envoi comme à la réception d'une facture, même transmise via Peppol.
            </p>
          </div>
        </h2>
        <form @submit.prevent="runSearch">
          <div class="field">
            <label for="directory-company">Rechercher via les identifiants de</label>
            <select id="directory-company" v-model.number="companyId" data-testid="directory-company-select">
              <option v-for="company in companies" :key="company.id" :value="company.id">
                {{ company.name }}
              </option>
            </select>
          </div>

          <div class="field">
            <label for="directory-resource">Type de recherche</label>
            <select id="directory-resource" v-model="resource" data-testid="directory-resource-select">
              <option value="siren">SIREN (entreprise)</option>
              <option value="siret">SIRET (établissement)</option>
              <option value="routing-code">Code de routage</option>
            </select>
          </div>

          <template v-if="resource === 'siren'">
            <input v-model="searchSiren" placeholder="SIREN" data-testid="directory-search-siren" />
            <input v-model="searchBusinessName" placeholder="Raison sociale" data-testid="directory-search-business-name" />
          </template>

          <template v-else-if="resource === 'siret'">
            <input v-model="searchSiret" placeholder="SIRET" data-testid="directory-search-siret" />
            <input v-model="searchName" placeholder="Nom de l'établissement" data-testid="directory-search-name" />
            <input v-model="searchPostalCode" placeholder="Code postal" data-testid="directory-search-postal-code" />
            <input v-model="searchLocality" placeholder="Ville" data-testid="directory-search-locality" />
          </template>

          <template v-else>
            <input v-model="searchRoutingIdentifier" placeholder="Identifiant de routage" data-testid="directory-search-routing-identifier" />
            <input v-model="searchRoutingCodeName" placeholder="Nom du code de routage" data-testid="directory-search-routing-code-name" />
            <input v-model="searchRoutingSiret" placeholder="SIRET" data-testid="directory-search-routing-siret" />
          </template>

          <div class="cluster">
            <button type="submit" class="btn-secondary" data-testid="directory-search-submit">
              Rechercher sur l'annuaire DGFIP
            </button>
            <button
              type="button"
              class="btn-secondary"
              data-testid="directory-peppol-search-submit"
              @click="runPeppolCheck"
            >
              Rechercher sur l'annuaire Peppol
            </button>
          </div>
        </form>
      </section>

      <section v-if="peppolCheckResult" class="card" data-testid="directory-peppol-check-result">
        <h2>Résultat Peppol — {{ peppolCheckIdentifier }}</h2>
        <p v-if="peppolCheckResult.error" role="alert">Erreur : {{ peppolCheckResult.error }}</p>
        <p v-else-if="peppolCheckResult.active">
          Actif dans l'annuaire Peppol — Access Point : <code>{{ peppolCheckResult.access_point }}</code>
        </p>
        <p v-else class="entity-list-empty">Non trouvé dans l'annuaire Peppol.</p>
      </section>

      <section v-if="searched" class="card">
        <p class="entity-sub">{{ totalResults }} résultat(s)</p>
        <table data-testid="directory-results-table">
          <thead v-if="resource === 'siren'">
            <tr>
              <th>SIREN</th>
              <th>Raison sociale</th>
              <th>Type d'entité</th>
              <th>Statut</th>
            </tr>
          </thead>
          <thead v-else-if="resource === 'siret'">
            <tr>
              <th>SIRET</th>
              <th>SIREN</th>
              <th>Nom</th>
              <th>Type d'établissement</th>
              <th>Statut</th>
            </tr>
          </thead>
          <thead v-else>
            <tr>
              <th>Identifiant de routage</th>
              <th>Nom du code</th>
              <th>SIRET</th>
              <th>Statut</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(entity, index) in results"
              :key="index"
              class="row-clickable"
              @click="openEntity(entity)"
              :data-testid="`directory-result-row-${index}`"
            >
              <template v-if="resource === 'siren'">
                <td>{{ entity.siren }}</td>
                <td>{{ entity.businessName }}</td>
                <td>{{ entity.entityType ?? '—' }}</td>
                <td>{{ adminStatusLabel(entity.administrativeStatus) }}</td>
              </template>
              <template v-else-if="resource === 'siret'">
                <td>{{ entity.siret }}</td>
                <td>{{ entitySiren(entity) ?? '—' }}</td>
                <td>{{ entity.name }}</td>
                <td>{{ entity.facilityType ?? '—' }}</td>
                <td>{{ adminStatusLabel(entity.administrativeStatus) }}</td>
              </template>
              <template v-else>
                <td>{{ entity.routingIdentifier }}</td>
                <td>{{ entity.routingCodeName ?? '—' }}</td>
                <td>{{ entitySiret(entity) ?? '—' }}</td>
                <td>{{ adminStatusLabel(entity.administrativeStatus) }}</td>
              </template>
            </tr>
            <tr v-if="results.length === 0">
              <td colspan="5" class="entity-list-empty">Aucun résultat.</td>
            </tr>
          </tbody>
        </table>
      </section>
    </template>

    <template v-else>
      <header class="page-header">
        <nav class="breadcrumb">
          <button type="button" class="back-link" data-testid="directory-detail-back" @click="goBackToSearch">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M15 6l-6 6 6 6" />
            </svg>
            Retour à la recherche
          </button>
          <template v-if="selectedLineIdentifier">
            <button type="button" class="breadcrumb-link" data-testid="directory-line-detail-back" @click="goBackToEntity">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <path d="M15 6l-6 6 6 6" />
              </svg>
              Retour à l'entrée d'annuaire
            </button>
          </template>
        </nav>
        <h1 v-if="!selectedLineIdentifier">Lignes d'annuaire DGFiP</h1>
        <h1 v-else>Ligne d'annuaire — {{ lineLabel(selectedLine ?? {}) }}</h1>
      </header>

      <section v-if="selectedLine" class="card" data-testid="directory-line-detail">
        <div class="modal-stats">
          <div class="modal-stat-card">
            <span class="modal-stat-label">Libellé</span>
            <span class="modal-stat-value">{{ lineLabel(selectedLine) }}</span>
          </div>
          <div class="modal-stat-card">
            <span class="modal-stat-label">Identifiant d'adressage</span>
            <span class="modal-stat-value">{{ selectedLine.addressingIdentifier ?? '—' }}</span>
            <span v-if="selectedLine.addressingSuffix" class="entity-sub">Suffixe : {{ selectedLine.addressingSuffix }}</span>
          </div>
          <div class="modal-stat-card">
            <span class="modal-stat-label">SIREN</span>
            <span class="modal-stat-value">{{ selectedLine.siren ?? selectedLine.legalUnit?.siren ?? '—' }}</span>
          </div>
          <div class="modal-stat-card">
            <span class="modal-stat-label">SIRET</span>
            <span class="modal-stat-value">{{ selectedLine.siret ?? selectedLine.facility?.siret ?? '—' }}</span>
          </div>
          <div class="modal-stat-card">
            <span class="modal-stat-label">Identifiant de routage</span>
            <span class="modal-stat-value">{{ selectedLine.routingIdentifier ?? '—' }}</span>
            <span v-if="selectedLine.routingCode?.routingIdentifierType" class="entity-sub">
              Type : {{ selectedLine.routingCode.routingIdentifierType }}
            </span>
          </div>
          <div class="modal-stat-card">
            <span class="modal-stat-label">Type de plateforme</span>
            <span class="modal-stat-value">{{ platformTypeLabel(selectedLine) }}</span>
          </div>
          <div class="modal-stat-card">
            <span class="modal-stat-label">Statut de la ligne</span>
            <span class="modal-stat-value">{{ selectedLine.directoryLineStatus ?? '—' }}</span>
          </div>
          <div class="modal-stat-card">
            <span class="modal-stat-label">Annuaire Peppol</span>
            <span class="modal-stat-value">
              <template v-if="selectedLine.peppol?.error">Erreur : {{ selectedLine.peppol.error }}</template>
              <template v-else-if="selectedLine.peppol?.active">Actif — {{ selectedLine.peppol.access_point }}</template>
              <template v-else>Non actif</template>
            </span>
          </div>
        </div>

        <div class="kv-columns" data-testid="directory-line-full-detail">
          <div class="kv-list">
            <h3 style="margin: 0 0 4px">Entité (raison sociale)</h3>
            <template v-if="selectedLine.legalUnit">
              <p><strong>Raison sociale :</strong> {{ selectedLine.legalUnit.businessName ?? '—' }}</p>
              <p><strong>SIREN :</strong> {{ selectedLine.legalUnit.siren ?? '—' }}</p>
              <p><strong>Type d'entité :</strong> {{ selectedLine.legalUnit.entityType ?? '—' }}</p>
              <p><strong>Statut administratif :</strong> {{ adminStatusLabel(selectedLine.legalUnit.administrativeStatus) }}</p>
              <p>
                <strong>Sollicitation commerciale interdite :</strong>
                {{ yesNo(selectedLine.legalUnit.instructions?.isSalesProspectingForbidden) }}
              </p>
            </template>
            <p v-else class="entity-sub">Non fourni par la plateforme agréée pour cette ligne.</p>

            <h3 style="margin: 16px 0 4px">Code de routage</h3>
            <template v-if="selectedLine.routingCode">
              <p><strong>Nom :</strong> {{ selectedLine.routingCode.routingCodeName ?? '—' }}</p>
              <p><strong>Identifiant :</strong> {{ selectedLine.routingCode.routingIdentifier ?? '—' }}</p>
              <p><strong>Type d'identifiant :</strong> {{ selectedLine.routingCode.routingIdentifierType ?? '—' }}</p>
              <p><strong>Statut administratif :</strong> {{ adminStatusLabel(selectedLine.routingCode.administrativeStatus) }}</p>
              <p v-if="selectedLine.routingCode.managesLegalCommitment !== undefined">
                <strong>Gère un numéro d'engagement juridique :</strong>
                {{ yesNo(selectedLine.routingCode.managesLegalCommitment) }}
              </p>
              <p v-if="formatAddress(selectedLine.routingCode.address)" data-testid="directory-line-routing-code-address">
                <strong>Adresse :</strong> {{ formatAddress(selectedLine.routingCode.address) }}
              </p>
            </template>
            <p v-else class="entity-sub">Aucun code de routage sur cette ligne.</p>
          </div>

          <div class="kv-list">
            <h3 style="margin: 0 0 4px">Établissement</h3>
            <template v-if="selectedLine.facility">
              <p><strong>Nom :</strong> {{ selectedLine.facility.name ?? '—' }}</p>
              <p><strong>SIRET :</strong> {{ selectedLine.facility.siret ?? '—' }}</p>
              <p>
                <strong>Type d'établissement :</strong>
                {{ selectedLine.facility.facilityType === 'P' ? 'Établissement principal' : selectedLine.facility.facilityType === 'S' ? 'Établissement secondaire' : '—' }}
              </p>
              <p><strong>Statut administratif :</strong> {{ adminStatusLabel(selectedLine.facility.administrativeStatus) }}</p>
              <p>
                <strong>Sollicitation commerciale interdite :</strong>
                {{ yesNo(selectedLine.facility.instructions?.isSalesProspectingForbidden) }}
              </p>
              <p v-if="formatAddress(selectedLine.facility.address)" data-testid="directory-line-facility-address">
                <strong>Adresse :</strong> {{ formatAddress(selectedLine.facility.address) }}
              </p>
            </template>
            <p v-else class="entity-sub">Non fourni par la plateforme agréée pour cette ligne.</p>

            <template v-if="selectedLine.facility?.b2gAdditionalData">
              <h3 style="margin: 16px 0 4px">Secteur public (B2G)</h3>
              <p>
                <strong>Gère les engagements juridiques :</strong>
                {{ yesNo(selectedLine.facility.b2gAdditionalData.managesLegalCommitmentCode) }}
              </p>
              <p>
                <strong>Gère les engagements ou codes de service :</strong>
                {{ yesNo(selectedLine.facility.b2gAdditionalData.managesLegalCommitmentOrServiceCode) }}
              </p>
              <p>
                <strong>Gère le statut de paiement :</strong>
                {{ yesNo(selectedLine.facility.b2gAdditionalData.managesPaymentStatus) }}
              </p>
              <p>
                <strong>Maîtrise d'ouvrage :</strong>
                {{ yesNo(selectedLine.facility.b2gAdditionalData.pm) }}
              </p>
              <p>
                <strong>Maîtrise d'ouvrage uniquement :</strong>
                {{ yesNo(selectedLine.facility.b2gAdditionalData.pmOnly) }}
              </p>
              <p>
                <strong>Requiert un code de service :</strong>
                {{ yesNo(selectedLine.facility.b2gAdditionalData.serviceCodeStatus) }}
              </p>
            </template>
          </div>
        </div>
      </section>
      <p v-else-if="selectedLineIdentifier && !error" class="entity-list-empty">
        Ligne d'annuaire introuvable.
      </p>

      <section v-if="detailEntity && !selectedLineIdentifier" class="card" data-testid="directory-detail">
        <div class="modal-stats">
          <template v-if="detailQuery.resource === 'siren'">
            <div class="modal-stat-card">
              <span class="modal-stat-label">SIREN</span>
              <span class="modal-stat-value">{{ detailEntity.siren }}</span>
            </div>
            <div class="modal-stat-card">
              <span class="modal-stat-label">Raison sociale</span>
              <span class="modal-stat-value">{{ detailEntity.businessName ?? '—' }}</span>
            </div>
            <div class="modal-stat-card">
              <span class="modal-stat-label">Type d'entité</span>
              <span class="modal-stat-value">{{ detailEntity.entityType ?? '—' }}</span>
            </div>
            <div class="modal-stat-card">
              <span class="modal-stat-label">Statut</span>
              <span class="modal-stat-value">{{ adminStatusLabel(detailEntity.administrativeStatus) }}</span>
            </div>
          </template>
          <template v-else-if="detailQuery.resource === 'siret'">
            <div class="modal-stat-card">
              <span class="modal-stat-label">SIRET</span>
              <span class="modal-stat-value">{{ detailEntity.siret }}</span>
            </div>
            <div class="modal-stat-card">
              <span class="modal-stat-label">SIREN</span>
              <span class="modal-stat-value">{{ entitySiren(detailEntity) ?? '—' }}</span>
            </div>
            <div class="modal-stat-card">
              <span class="modal-stat-label">Nom</span>
              <span class="modal-stat-value">{{ detailEntity.name ?? '—' }}</span>
            </div>
            <div class="modal-stat-card">
              <span class="modal-stat-label">Statut</span>
              <span class="modal-stat-value">{{ adminStatusLabel(detailEntity.administrativeStatus) }}</span>
            </div>
          </template>
          <template v-else>
            <div class="modal-stat-card">
              <span class="modal-stat-label">Identifiant de routage</span>
              <span class="modal-stat-value">{{ detailEntity.routingIdentifier }}</span>
            </div>
            <div class="modal-stat-card">
              <span class="modal-stat-label">Nom du code</span>
              <span class="modal-stat-value">{{ detailEntity.routingCodeName ?? '—' }}</span>
            </div>
            <div class="modal-stat-card">
              <span class="modal-stat-label">SIRET</span>
              <span class="modal-stat-value">{{ entitySiret(detailEntity) ?? '—' }}</span>
            </div>
            <div class="modal-stat-card">
              <span class="modal-stat-label">Statut</span>
              <span class="modal-stat-value">{{ adminStatusLabel(detailEntity.administrativeStatus) }}</span>
            </div>
          </template>
        </div>

        <h3>Lignes d'annuaire pour cette entité</h3>
        <p v-if="directoryLinesLoading" class="entity-sub" data-testid="directory-lines-loading">
          Chargement des lignes d'annuaire…
        </p>
        <p v-else-if="directoryLinesError" role="alert" data-testid="directory-lines-error">
          {{ directoryLinesError }}
        </p>
        <table v-else-if="directoryLines.length" data-testid="directory-lines-table">
          <thead>
            <tr>
              <th>Libellé</th>
              <th>Identifiant d'adressage</th>
              <th>SIREN</th>
              <th>SIRET</th>
              <th>Identifiant de routage</th>
              <th>Type de plateforme</th>
              <th>Statut</th>
              <th>Annuaire Peppol</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(line, index) in directoryLines"
              :key="index"
              class="row-clickable"
              @click="openLine(line)"
              :data-testid="`directory-line-row-${index}`"
            >
              <td>{{ lineLabel(line) }}</td>
              <td>
                {{ line.addressingIdentifier ?? '—' }}
                <span v-if="line.addressingSuffix" class="entity-sub">Suffixe {{ line.addressingSuffix }}</span>
              </td>
              <td>{{ line.siren ?? line.legalUnit?.siren ?? '—' }}</td>
              <td>{{ line.siret ?? line.facility?.siret ?? '—' }}</td>
              <td>{{ line.routingIdentifier ?? '—' }}</td>
              <td>{{ platformTypeLabel(line) }}</td>
              <td>{{ line.directoryLineStatus ?? '—' }}</td>
              <td :data-testid="`directory-line-peppol-${index}`">
                <template v-if="line.peppol?.error">
                  <span class="entity-sub">Erreur : {{ line.peppol.error }}</span>
                </template>
                <template v-else-if="line.peppol?.active">
                  Actif — {{ line.peppol.access_point }}
                </template>
                <template v-else>Non actif</template>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else class="entity-list-empty">Aucune ligne d'annuaire.</p>
      </section>
      <p v-else-if="!selectedLineIdentifier && !error" class="entity-list-empty">Entrée introuvable dans l'annuaire.</p>
    </template>
  </main>
</template>
