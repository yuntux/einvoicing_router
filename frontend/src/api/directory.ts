import { apiFetch } from './http'

export type DirectoryResource = 'siren' | 'siret' | 'routing-code'

export interface DirectorySearchParams {
  company_id: number
  resource: DirectoryResource
  siren?: string
  business_name?: string
  siret?: string
  name?: string
  postal_code?: string
  locality?: string
  routing_identifier?: string
  routing_code_name?: string
}

// Formes brutes du contrat AFNOR (`legalUnitPayloadHistory`/`facilityPayloadHistory`/
// `routingCodePayloadHistoryLegalUnitFacility`) — un seul type large plutôt que trois
// interfaces strictes, chaque `resource` ne peuplant qu'un sous-ensemble des champs.
export interface DirectoryEntity {
  siren?: string
  siret?: string
  businessName?: string
  name?: string
  entityType?: string
  facilityType?: string
  administrativeStatus?: string
  routingIdentifier?: string
  routingIdentifierType?: string
  routingCodeName?: string
  address?: {
    addressLines?: string[]
    postalCode?: string
    locality?: string
    countrySubdivision?: string
  }
  legalUnit?: { siren?: string; businessName?: string }
  facility?: { siret?: string; name?: string }
}

export interface DirectorySearchResult {
  results: DirectoryEntity[]
  totalNumberOfResults: number
}

// Ajouté côté routeur (§ colonne "Annuaire Peppol"), jamais fourni par SuperPDP :
// résolution DNS indépendante contre le réseau PEPPOL (`peppol_service`).
export interface DirectoryLinePeppolStatus {
  active: boolean
  access_point: string | null
  error: string | null
}

export interface DirectoryLineAddress {
  addressLine1?: string
  addressLine2?: string
  addressLine3?: string
  postalCode?: string
  locality?: string
  countrySubdivision?: string
  countryCode?: string
  countryName?: string
}

export interface DirectoryLineRoutingCode {
  routingCodeName?: string
  routingIdentifier?: string
  routingIdentifierType?: string
  administrativeStatus?: string
  // Booléen brut du contrat, jamais renvoyé pour une entité privée (§ description
  // officielle : "only returned if the directory line is defined for a public
  // structure") — n'existe donc jamais en même temps qu'une valeur "Public" absente.
  managesLegalCommitment?: boolean
  address?: DirectoryLineAddress
}

// `platformType` (norme UNCL 3035) : "WK" = plateforme de dématérialisation
// partenaire (PA), "DFH" = portail public de facturation (PPF, Chorus Pro).
export type DirectoryLinePlatformType = 'WK' | 'DFH'

export interface DirectoryLineInstructions {
  isSalesProspectingForbidden?: boolean
}

// Uniquement pour une structure publique (secteur B2G), § description officielle de
// chacun de ces champs — jamais renvoyé pour une entité privée.
export interface DirectoryLineB2gData {
  managesLegalCommitmentCode?: boolean
  managesLegalCommitmentOrServiceCode?: boolean
  managesPaymentStatus?: boolean
  pm?: boolean
  pmOnly?: boolean
  serviceCodeStatus?: boolean
}

export interface DirectoryLineLegalUnit {
  siren?: string
  businessName?: string
  entityType?: string
  administrativeStatus?: string
  instructions?: DirectoryLineInstructions
}

export interface DirectoryLineFacility {
  siren?: string
  siret?: string
  name?: string
  facilityType?: string
  administrativeStatus?: string
  address?: DirectoryLineAddress
  instructions?: DirectoryLineInstructions
  b2gAdditionalData?: DirectoryLineB2gData
}

export interface DirectoryLine {
  addressingIdentifier?: string
  addressingSuffix?: string
  siren?: string
  siret?: string
  routingIdentifier?: string
  directoryLineStatus?: string
  platformType?: DirectoryLinePlatformType
  routingCode?: DirectoryLineRoutingCode
  // Peuplés grâce à `include: ["siren", "siret", "routingCode"]` (§ backend
  // `DirectoryLinesRequest`) — portent le libellé lisible (raison sociale/nom
  // d'établissement) et le détail complet du contrat, absents des seuls
  // identifiants bruts de la ligne elle-même.
  legalUnit?: DirectoryLineLegalUnit
  facility?: DirectoryLineFacility
  peppol?: DirectoryLinePeppolStatus
}

export interface DirectoryLinesResult {
  results: DirectoryLine[]
  totalNumberOfResults: number
}

export function searchDirectory(params: DirectorySearchParams): Promise<DirectorySearchResult> {
  return apiFetch('/api/ihm/directory/search', { method: 'POST', json: params }, 'Failed to search directory')
}

export function listDirectoryLines(params: {
  company_id: number
  siren?: string
  siret?: string
}): Promise<DirectoryLinesResult> {
  return apiFetch('/api/ihm/directory/lines', { method: 'POST', json: params }, 'Failed to list directory lines')
}

/** Vérification directe dans l'annuaire Peppol (§ bouton "Rechercher sur l'annuaire
 * Peppol") — pas de `company_id` (résolution DNS, indépendante de SuperPDP), et pas
 * besoin d'avoir trouvé l'entité côté DGFIP au préalable. */
export function checkPeppolStatus(identifier: string): Promise<DirectoryLinePeppolStatus> {
  return apiFetch(
    '/api/ihm/directory/peppol-check',
    { method: 'POST', json: { identifier } },
    'Failed to check Peppol status',
  )
}
