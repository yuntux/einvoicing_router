"""Génération des flux CDAR (Cross Domain Acknowledgement and Response, XP Z12-013,
§ 4.2/NF7, lot 6) à partir des messages de cycle de vie saisis dans le routeur —
s'appuie sur `pyfrctc.generate_cdar` pour la génération XML + validation XSD (locale,
sans réseau) et, optionnellement, la validation schématron (nécessite un serveur Saxon,
`settings.saxon_server_url`).

Note de conception : le mapping exact des clés `MDT-*` attendues par pyfrctc n'est
documenté par aucune spécification publique complète à ce jour — les valeurs choisies
ci-dessous ont été validées localement contre le XSD officiel embarqué dans pyfrctc
(`check_xsd=True`) pour les statuts avec et sans détail/paiement, mais restent à
recalibrer lors des premiers essais réels contre le bac à sable (§ 10.4)."""

from datetime import date, datetime

from pyfrctc import pyfrctc as core

from app.config import settings
from app.models.invoicing import Invoice
from app.models.lifecycle import LifecycleEventPayment
from app.models.referential import Company
from app.services.lifecycle_catalog import STATUS_CATALOG

GUIDELINE_ID = "urn:cen.eu:EN16931:2017#compliant#urn:factur-x.eu:1p0:basic"
BUSINESS_PROCESS_ID = "urn:factur-x.eu:1p0:basic"
ACKNOWLEDGEMENT_TYPE_CODE = "494"

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
) -> dict:
    status_info = STATUS_CATALOG[status]
    now = datetime.utcnow()

    data_dict: dict = {
        "MDT-2": BUSINESS_PROCESS_ID,
        "MDT-3": GUIDELINE_ID,
        "MDT-4": f"cdar-{invoice.certified_platform_flow_id}-{status}-{int(now.timestamp())}",
        "MDT-8": now,
        "MDT-21": "BY",
        # Émetteur de la facture d'origine (fournisseur) — brut, cf. Invoice (§ 6.1).
        "MDT-38": {"0002": invoice.emitter_siren},
        "MDT-39": invoice.emitter_siret or invoice.emitter_siren,
        "MDT-40": "SE",
        # Destinataire de la facture d'origine (l'entreprise gérée, côté achat) —
        # identifiant annuaire de la plateforme certifiée si renseigné (cf.
        # `Company.certified_platform_directory_id`), sinon le SIREN légal : un bac à
        # sable AFNOR peut immatriculer l'entreprise sous un identifiant technique qui
        # n'est pas un SIREN valide, auquel cas l'annuaire ne reconnaît pas le SIREN
        # légal et échoue à déterminer la règle de traitement/refuse l'émission.
        "MDT-57": {"0002": buyer_company.certified_platform_directory_id or buyer_company.siren},
        "MDT-58": buyer_company.name,
        "MDT-59": "BY",
        "MDT-73": "superpdp",
        "MDT-73-1": "EM",
        "MDT-74": False,
        "MDT-77": ACKNOWLEDGEMENT_TYPE_CODE,
        "MDT-78": now,
        # Numéro de facture métier (pas l'identifiant technique du flux AFNOR) : c'est
        # ce que la contrepartie connaît et sait rapprocher de sa propre facture — cf.
        # `l10n_fr_einvoicing` (`fr_einvoicing_event._prepare_xml_data`), qui met ici
        # `invoice.ref`/`invoice.name`, jamais un identifiant de flux interne.
        "MDT-87": invoice.invoice_number,
        "MDT-91": "380",
        "MDT-100": now.date(),
        "MDT-105": status_info.cdar_code,
        "MDT-106": status_info.label,
        # Émetteur du message d'accusé lui-même : l'entreprise gérée (côté achat) —
        # même identifiant que MDT-57, cf. ci-dessus.
        "MDT-129": {"0002": buyer_company.certified_platform_directory_id or buyer_company.siren},
    }
    if status_info.mdt88_code:
        data_dict["MDT-88"] = status_info.mdt88_code

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
