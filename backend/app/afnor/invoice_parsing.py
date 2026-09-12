"""Extraction des champs métier d'une facture (émetteur, montants, numéro...) depuis
le fichier facture lui-même (CII/Factur-X ou UBL).

Le Metadata d'un flux AFNOR (`GET /flows/{id}?docType=Metadata` de l'API
"afnor-flow", norme XP Z12-013 — cf. schéma officiel fourni par l'utilisateur) ne
porte que l'enveloppe de transport du flux (flowId, flowSyntax, processingRule,
flowDirection, flowType, acknowledgement...) : aucune donnée métier de la facture.
Ces champs n'existent que dans le fichier lui-même (`docType=Original`), au format
déclaré par `flowSyntax`."""

from dataclasses import dataclass
from datetime import date

from lxml import etree

# Parseur XML durci (CWE-611) : `etree.fromstring` résout par défaut les entités
# externes et charge les DTD référencées, ce qui exposerait le routeur à une
# exfiltration de fichiers locaux ou un déni de service (entity expansion) via un
# champ de facture UBL reçu d'un fournisseur tiers, pas nécessairement de confiance
# — `resolve_entities=False` désactive la substitution d'entités, `no_network=True`
# interdit toute résolution réseau, `load_dtd=False` empêche même le chargement
# local d'une DTD référencée.
_SAFE_XML_PARSER = etree.XMLParser(
    resolve_entities=False,
    no_network=True,
    load_dtd=False,
    dtd_validation=False,
    huge_tree=False,
)


@dataclass
class ParsedInvoiceFields:
    emitter_siren: str | None = None
    emitter_siret: str | None = None
    emitter_name: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    amount_total: float | None = None
    amount_excl_tax: float | None = None
    # Montant de TVA déclaré dans le fichier (ram:TaxTotalAmount / cac:TaxTotal ⁄
    # cbc:TaxAmount) — jamais recalculé par soustraction (amount_total - amount_excl_tax),
    # qui accumule les erreurs de représentation flottante (ex. 303.3299999999999) et
    # ignore les cas où la facture porte un arrondi ou un acompte qui invalident cette
    # égalité (cf. `ram:RoundingAmount`/`ram:TotalPrepaidAmount` en CII).
    amount_tax: float | None = None
    currency: str | None = None
    # Code UNTDID 1001 (ex. "380" facture, "381" avoir) — cf. `_invoice_type_from_code`.
    type_code: str | None = None


# Scheme UN/EDIFACT (liste ISO 6523 des "ICD") utilisés en France pour identifier une
# entreprise dans les factures CII/Factur-X (Chorus Pro / FNFE-MPE) :
# 0002 = SIREN (SIRENE), 0009 = SIRET.
_SIREN_SCHEME = "0002"
_SIRET_SCHEME = "0009"


def invoice_type_from_code(type_code: str | None) -> str:
    """"381" = avoir (UNTDID 1001), tout le reste est traité comme une facture."""
    return "credit_note" if type_code == "381" else "invoice"


def _siren_siret_from_global_ids(global_id_children) -> tuple[str | None, str | None]:
    siren = siret = None
    for scheme, value in global_id_children:
        if scheme == _SIREN_SCHEME:
            siren = value
        elif scheme == _SIRET_SCHEME:
            siret = value
    if siren is None and siret and len(siret) == 14:
        siren = siret[:9]
    return siren, siret


def _decimal_or_none(currency_element) -> float | None:
    amount = getattr(currency_element, "_amount", None)
    if amount in (None, ""):
        return None
    return float(amount)


def _tax_total_amount(summation) -> float | None:
    """`drafthorse` fait cohabiter deux champs sur le même tag XML `TaxTotalAmount` :
    `tax_total` (`CurrencyField`, profil BASIC) et `tax_total_other_currency`
    (`MultiCurrencyField`, profil EXTENDED, pour le cas rare d'un second montant de
    TVA dans une autre devise). Les deux étant enregistrés sur le même tag, le
    parseur route la valeur vers le conteneur multi-devise plutôt que vers le champ
    simple — `summation.tax_total` reste vide alors que la valeur est bien présente
    dans `summation.tax_total_other_currency.children`. Contournement : lire l'un
    puis l'autre plutôt que de supposer que le champ "normal" est fiable."""
    direct = _decimal_or_none(summation.tax_total)
    if direct is not None:
        return direct
    children = getattr(summation.tax_total_other_currency, "children", None)
    if not children:
        return None
    amount, _currency = children[0]
    try:
        return float(amount)
    except (TypeError, ValueError):
        return None


def _cii_xml_from_facturx_pdf(file_content: bytes) -> bytes:
    """Un flux `flowSyntax=Factur-X` est un PDF/A-3 avec l'XML CII embarqué comme
    pièce jointe — `drafthorse` sait en écrire (attach_xml) mais pas en extraire ;
    on utilise `factur-x` (implémentation de référence FNFE-MPE) pour ça."""
    from facturx import get_xml_from_pdf

    _filename, xml_bytes = get_xml_from_pdf(file_content, check_xsd=False)
    if not xml_bytes:
        raise ValueError("Aucun XML Factur-X/CII trouvé dans le PDF")
    return xml_bytes


def parse_cii(file_content: bytes) -> ParsedInvoiceFields:
    """CII et Factur-X partagent le même schéma métier une fois l'XML CII en main
    — cf. bibliothèque `drafthorse` (modèle objet complet de l'EN 16931/CII)."""
    from drafthorse.models.document import Document

    doc = Document.parse(file_content, strict=False)
    seller = doc.trade.agreement.seller
    siren, siret = _siren_siret_from_global_ids(seller.global_id.children)
    summation = doc.trade.settlement.monetary_summation

    invoice_date = doc.header.issue_date_time._value
    return ParsedInvoiceFields(
        emitter_siren=siren,
        emitter_siret=siret,
        emitter_name=str(seller.name) or None,
        invoice_number=str(doc.header.id) or None,
        invoice_date=invoice_date.date() if hasattr(invoice_date, "date") else invoice_date,
        amount_total=_decimal_or_none(summation.grand_total),
        amount_excl_tax=_decimal_or_none(summation.tax_basis_total),
        amount_tax=_tax_total_amount(summation),
        currency=str(doc.trade.settlement.currency_code) or None,
        type_code=str(doc.header.type_code) or None,
    )


def parse_facturx(file_content: bytes) -> ParsedInvoiceFields:
    """Désembarque l'XML CII du PDF Factur-X puis réutilise `parse_cii`."""
    xml_bytes = _cii_xml_from_facturx_pdf(file_content)
    return parse_cii(xml_bytes)


_UBL_NS = {
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
}


def parse_ubl(file_content: bytes) -> ParsedInvoiceFields:
    root = etree.fromstring(file_content, parser=_SAFE_XML_PARSER)

    def text(path: str) -> str | None:
        el = root.find(path, _UBL_NS)
        return el.text.strip() if el is not None and el.text else None

    def amount(path: str) -> float | None:
        value = text(path)
        return float(value) if value is not None else None

    supplier_party = root.find("cac:AccountingSupplierParty/cac:Party", _UBL_NS)
    emitter_name = emitter_siren = emitter_siret = None
    if supplier_party is not None:
        legal_name = supplier_party.find(
            "cac:PartyLegalEntity/cbc:RegistrationName", _UBL_NS
        )
        if legal_name is None:
            legal_name = supplier_party.find("cac:PartyName/cbc:Name", _UBL_NS)
        emitter_name = legal_name.text.strip() if legal_name is not None and legal_name.text else None

        company_id = supplier_party.find("cac:PartyLegalEntity/cbc:CompanyID", _UBL_NS)
        if company_id is not None and company_id.text:
            identifier = company_id.text.strip()
            if len(identifier) == 14:
                emitter_siret, emitter_siren = identifier, identifier[:9]
            elif len(identifier) == 9:
                emitter_siren = identifier

    invoice_date_text = text("cbc:IssueDate")

    return ParsedInvoiceFields(
        emitter_siren=emitter_siren,
        emitter_siret=emitter_siret,
        emitter_name=emitter_name,
        invoice_number=text("cbc:ID"),
        invoice_date=date.fromisoformat(invoice_date_text) if invoice_date_text else None,
        amount_total=amount("cac:LegalMonetaryTotal/cbc:PayableAmount"),
        amount_excl_tax=amount("cac:LegalMonetaryTotal/cbc:TaxExclusiveAmount"),
        amount_tax=amount("cac:TaxTotal/cbc:TaxAmount"),
        currency=text("cbc:DocumentCurrencyCode"),
        type_code=text("cbc:InvoiceTypeCode"),
    )


def parse_invoice_fields(file_content: bytes, flow_syntax: str | None) -> ParsedInvoiceFields:
    """Ne lève jamais : une facture illisible/malformée ne doit pas faire échouer
    tout le cycle de polling (cf. app.scheduler.polling_job) — retourne un
    `ParsedInvoiceFields` vide (tous champs `None`) dans ce cas, la facture reste
    alors identifiée par son seul `flow_id` (cf. invoice_ingestion_service)."""
    try:
        if flow_syntax == "CII":
            return parse_cii(file_content)
        if flow_syntax == "Factur-X":
            return parse_facturx(file_content)
        if flow_syntax == "UBL":
            return parse_ubl(file_content)
    except Exception:
        pass
    return ParsedInvoiceFields()
