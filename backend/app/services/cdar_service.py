"""Génération des flux CDAR (Cross Domain Acknowledgement and Response, XP Z12-013,
§ 4.2/NF7, lot 6) à partir des messages de cycle de vie saisis dans le routeur —
s'appuie sur `pyfrctc.generate_cdar` pour la génération XML + validation XSD (locale,
sans réseau) et, optionnellement, la validation schématron (nécessite un serveur Saxon,
`settings.saxon_server_url`).

Note de conception : le mapping exact des clés `MDT-*` attendues par pyfrctc n'est
documenté par aucune spécification publique complète à ce jour — les valeurs ci-dessous
ont été recalées sur l'implémentation de référence Akretion `l10n_fr_einvoicing`
(`fr_einvoicing_event._prepare_xml_data`, module Odoo, coté achat/"purchase" — seul cas
géré par ce service, cf. `lifecycle_service`) après qu'un essai réel contre le bac à
sable SuperPDP a échoué avec `no matching invoices found` : `IssuerTradeParty`
(MDT-38/39/40) et `RecipientTradeParty` (MDT-57/58/59) étaient inversés (l'acheteur qui
émet l'accusé doit être l'*Issuer*, le vendeur qui le reçoit le *Recipient* — pas
l'inverse, qui empêchait SuperPDP de corréler l'accusé à la facture)."""

from datetime import date, datetime

from pyfrctc import pyfrctc as core

from app.config import settings
from app.models.invoicing import Invoice
from app.models.lifecycle import LifecycleEventPayment
from app.models.referential import Company
from app.services.lifecycle_catalog import STATUS_CATALOG

GUIDELINE_ID = "urn.cpro.gouv.fr:1p0:CDV:invoice"
# "REGULATED" : nos flux sont des factures B2B/B2G soumises à la réforme française
# de facturation électronique obligatoire — pas de destinataire PPF unique en
# GlobalID 0000/schemeID 0238 (seul cas où une chaîne <3 caractères serait admise,
# cf. BR-FR-CDV-CL-01) ni de flux hors mandat (B2C, international, etc.).
BUSINESS_PROCESS_ID = "REGULATED"
# "23" (Phase Traitement) : le seul des deux codes autorisés (BR-FR-CDV-09,
# "23"/"305") compatible avec nos rôles fixes MDT-21="BY"/MDT-40="BY" — "305"
# exige un rôle "WK" (BR-FR-CDV-CL-02/03) qu'on n'utilise jamais.
ACKNOWLEDGEMENT_TYPE_CODE = "23"

# Index inverse de `STATUS_CATALOG` par `cdar_code` (MDT-105/MDT-106 côté flux entrant,
# cf. `resolve_status_key`) — construit une fois au chargement du module. Aucun statut
# du catalogue ne partage le même `cdar_code`, la correspondance est donc univoque.
_STATUS_KEY_BY_CDAR_CODE: dict[str, str] = {
    info.cdar_code: key for key, info in STATUS_CATALOG.items()
}


def build_data_dict(
    *,
    invoice: Invoice,
    buyer_company: Company,
    status: str,
    reason: str | None = None,
    action: str | None = None,
    comment: str | None = None,
    payments: list[LifecycleEventPayment] | None = None,
    attachments: list[dict] | None = None,
) -> dict:
    status_info = STATUS_CATALOG[status]
    now = datetime.utcnow()

    data_dict: dict = {
        "MDT-2": BUSINESS_PROCESS_ID,
        "MDT-3": GUIDELINE_ID,
        # Format aligné sur `l10n_fr_einvoicing` (`{inv_number}_{type_code}_{date}#
        # {status_code}_{timestamp}`) — notre ancien format libre
        # (`cdar-{flow_id}-{status}-{epoch}`) ne suit aucune convention documentée ;
        # SuperPDP semble parser CETTE valeur pour corréler l'accusé à la facture
        # (`no matching invoices found` avec l'ancien format, alors que le contenu de
        # `ReferenceReferencedDocument` était par ailleurs correct).
        "MDT-4": (
            f"{invoice.invoice_number}_380_{invoice.invoice_date.isoformat()}"
            f"#{status_info.cdar_code}_{now.strftime('%Y%m%d%H%M%S')}"
        ),
        "MDT-8": now,
        # Côté achat, l'émetteur de CET ACCUSÉ est nous (l'acheteur, "BY") — jamais le
        # fournisseur — cf. `l10n_fr_einvoicing` : `sender_role_code = "BY"` pour tout
        # `invoice.is_purchase_document()`, réutilisé tel quel pour MDT-21 ET MDT-40.
        "MDT-21": "BY",
        # Émetteur DE L'ACCUSÉ (nous, l'acheteur) — identifiant annuaire de la
        # plateforme certifiée si renseigné (cf. `Company.certified_platform_directory_id`),
        # sinon le SIREN légal : un bac à sable AFNOR peut immatriculer l'entreprise sous
        # un identifiant technique qui n'est pas un SIREN valide.
        "MDT-38": {"0002": buyer_company.certified_platform_directory_id or buyer_company.siren},
        "MDT-39": buyer_company.name,
        "MDT-40": "BY",
        # Destinataire DE L'ACCUSÉ (le fournisseur, émetteur de la facture d'origine) —
        # brut, cf. Invoice (§ 6.1).
        "MDT-57": {"0002": invoice.emitter_siren},
        "MDT-58": (invoice.partner.name if invoice.partner else None) or invoice.emitter_siren,
        "MDT-59": "SE",
        # Adresse électronique du destinataire (le fournisseur) — idéalement la ligne
        # d'annuaire réelle du fournisseur (`fr_directory_line_identifier` côté
        # `l10n_fr_einvoicing`, obtenue par consultation de l'annuaire AFNOR à la
        # réception de la facture) ; non capturée aujourd'hui côté routeur (§ TODO),
        # on retombe sur son SIREN sous le même schéma "0002" que MDT-57 plutôt que
        # sur la valeur "superpdp"/"EM" précédente, qui n'avait aucun sens.
        "MDT-73": invoice.emitter_siren,
        "MDT-73-1": "0002",
        "MDT-74": False,
        "MDT-77": ACKNOWLEDGEMENT_TYPE_CODE,
        "MDT-78": now,
        # Numéro de facture métier (pas l'identifiant technique du flux AFNOR) : c'est
        # ce que la contrepartie connaît et sait rapprocher de sa propre facture — cf.
        # `l10n_fr_einvoicing` (`fr_einvoicing_event._prepare_xml_data`), qui met ici
        # `invoice.ref`/`invoice.name`, jamais un identifiant de flux interne.
        "MDT-87": invoice.invoice_number,
        "MDT-91": "380",
        # Date d'émission de la facture D'ORIGINE référencée (`ReferenceReferencedDocument/
        # FormattedIssueDateTime`) — jamais la date d'émission DE CET ACCUSÉ (qui n'a pas
        # de champ dédié ici) : `l10n_fr_einvoicing` y met `invoice.invoice_date`, jamais
        # `now`. Envoyer la date du jour à la place de la vraie date de la facture
        # empêchait vraisemblablement SuperPDP de la retrouver ("no matching invoices found").
        "MDT-100": invoice.invoice_date,
        "MDT-105": status_info.cdar_code,
        "MDT-106": status_info.label,
        # Émetteur de la facture D'ORIGINE référencée (le fournisseur, pas nous) :
        # `pyfrctc.parse_cdar_from_raw` mappe explicitement MDT-129 sur la clé
        # "invoice_issuer" (`ram:ReferenceReferencedDocument/ram:IssuerTradeParty`),
        # même valeur que MDT-57 ci-dessus (`issuer_siren = partner_siren` côté
        # `l10n_fr_einvoicing` pour un document d'achat).
        "MDT-129": {"0002": invoice.emitter_siren},
    }
    if status_info.mdt88_code:
        data_dict["MDT-88"] = status_info.mdt88_code
    if invoice.received_at:
        # Optionnel côté `pyfrctc` (rendu seulement si la clé est présente), mais
        # renseigné dans l'exemple de référence `l10n_fr_einvoicing` — date à laquelle
        # NOUS avons reçu la facture d'origine, pas sa date d'émission (MDT-100).
        data_dict["MDT-95"] = invoice.received_at
    if attachments:
        # Pièces jointes (§ 4.2, MDT-96) — `l10n_fr_einvoicing` les autorise sur
        # n'importe quel statut saisissable manuellement, sans restriction
        # particulière (`fr_einvoicing_event_manual.attachment_ids`, aucune condition
        # liée au statut dans `_compute_required_fields`) : même comportement ici.
        # Chaque élément : `{"bin": bytes, "filename": str, "mime_type": str}` (clé
        # optionnelle), même forme que `pyfrctc.parse_cdar_from_raw`
        # (`"attachments"`) en lecture.
        data_dict["MDT-96"] = attachments

    if reason or action or comment:
        doc_status: dict = {}
        if reason:
            doc_status["MDT-113"] = reason
        if action:
            doc_status["MDT-121"] = action
        if comment:
            doc_status["MDT-126"] = comment
        data_dict["MDG-37"] = [doc_status]
    elif payments:
        doc_status = {
            "MDG-43": [
                {
                    "MDT-215": {"float": payment.amount, "currency": payment.currency},
                    "MDT-219": payment.payment_date,
                }
                for payment in payments
            ]
        }
        data_dict["MDG-37"] = [doc_status]

    return data_dict


def generate(data_dict: dict) -> bytes:
    return core.generate_cdar(
        data_dict,
        check_xsd=True,
        check_schematron=bool(settings.saxon_server_url),
        saxon_server_url=settings.saxon_server_url,
    )


def parse(xml_bytes: bytes) -> dict:
    """Parse un CDAR entrant (§ 4.2) : dict à clés lisibles (`invoice_number`,
    `status_code`, `doc_status`...), symétrique du dict `MDT-*` que `build_data_dict`
    construit pour l'émission — cf. `pyfrctc.parse_cdar` (= `parse_cdar_raw` +
    `parse_cdar_from_raw`). Valide contre le XSD officiel comme `generate()`."""
    return core.parse_cdar(
        xml_bytes,
        check_xsd=True,
        check_schematron=bool(settings.saxon_server_url),
        saxon_server_url=settings.saxon_server_url,
    )


def resolve_status_key(cdar_code: str) -> str | None:
    """Retrouve la clé interne de `STATUS_CATALOG` dont `cdar_code` correspond au
    `status_code` (MDT-105) d'un CDAR entrant — `None` si le code n'est pas reconnu
    (catalogue incomplet ou évolution de la norme, ne doit jamais faire échouer
    l'ingestion, cf. `lifecycle_service.create_incoming_event`)."""
    return _STATUS_KEY_BY_CDAR_CODE.get(cdar_code)


def _json_safe(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        # Le contenu binaire d'une pièce jointe (MDT-96, "bin") est déjà persisté à
        # part sur disque (`LifecycleEventAttachment.file_path`, § 4.2) — pas de
        # raison de le dupliquer (et bytes n'est de toute façon pas sérialisable) dans
        # la colonne JSON `AfnorFlow.data_dict`, qui n'a besoin que des métadonnées.
        return f"<{len(value)} bytes>"
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


def to_json_safe(data_dict: dict) -> dict:
    """Copie sérialisable de `data_dict` (dates/datetimes -> ISO 8601), pour stockage
    dans `AfnorFlow.data_dict` (colonne JSON) — `data_dict` lui-même reste inchangé,
    pyfrctc attendant des objets `date`/`datetime` natifs."""
    return _json_safe(data_dict)
