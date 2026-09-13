"""Catalogue fermé des statuts de cycle de vie AFNOR XP Z12-013 (spec.md § 4.2).

Source unique de vérité, réutilisée par `LifecycleService` et exposée à l'IHM
(`GET /api/ihm/lifecycle-catalog`) pour que le formulaire de saisie reste synchronisé
avec les règles métier plutôt que de les dupliquer côté frontend.
"""

from typing import Literal, NamedTuple

ManualSide = Literal["purchase", "sale"]


class StatusInfo(NamedTuple):
    label: str
    cdar_code: str
    mdt88_code: str | None = None
    # None = non saisissable manuellement (technique, reçu, ou auto-calculé).
    manual_side: ManualSide | None = None
    requires_detail: bool = False
    requires_confirmation: bool = False
    # Sous-ensemble de `REASONS` accepté pour CE statut par le schématron officiel
    # SuperPDP (`BR-FR-CDV-CL-09`, cf. pyfrctc `cdar-schematron/BR-FR-CDV-Schematron-
    # CDAR.xslt`) — un motif valide pour un autre statut (ex. "NON_CONFORME" pour
    # "dispute"/"refused") est rejeté par la plateforme pour "suspended". Vide tant
    # que `requires_detail` est faux.
    allowed_reasons: tuple[str, ...] = ()


STATUS_CATALOG: dict[str, StatusInfo] = {
    # Statuts techniques, émis par la plateforme — jamais saisis dans l'IHM.
    "submitted": StatusInfo("Déposée", "200"),
    "ap_sent": StatusInfo("Émise par la plateforme", "201"),
    "ap_received": StatusInfo("Reçue par la plateforme", "202"),
    "ap_available": StatusInfo("Mise à disposition", "203"),
    # Statut métier auto-calculé à réception — non saisissable manuellement.
    "in_hand": StatusInfo("Prise en charge", "204", mdt88_code="45"),
    # Statuts métier saisissables manuellement (achat).
    "approved": StatusInfo("Approuvée", "205", mdt88_code="1", manual_side="purchase"),
    "partially_approved": StatusInfo(
        "Partiellement approuvée",
        "206",
        mdt88_code="49",
        manual_side="purchase",
        requires_detail=True,
        allowed_reasons=(
            "AUTRE", "CMD_ERR", "SIRET_ERR", "CODE_ROUTAGE_ERR", "REF_CT_ABSENT", "REF_ERR",
            "PU_ERR", "REM_ERR", "QTE_ERR", "ART_ERR", "MODPAI_ERR", "QUALITE_ERR", "LIVR_INCOMP",
        ),
    ),
    "dispute": StatusInfo(
        "En litige", "207", mdt88_code="46", manual_side="purchase", requires_detail=True,
        allowed_reasons=(
            "AUTRE", "COORD_BANC_ERR", "TX_TVA_ERR", "MONTANTTOTAL_ERR", "CALCUL_ERR", "NON_CONFORME",
            "DOUBLON", "DEST_INC", "DEST_ERR", "TRANSAC_INC", "EMMET_INC", "CONTRAT_TERM", "DOUBLE_FACT",
            "CMD_ERR", "ADR_ERR", "SIRET_ERR", "CODE_ROUTAGE_ERR", "REF_CT_ABSENT", "REF_ERR", "PU_ERR",
            "REM_ERR", "QTE_ERR", "ART_ERR", "MODPAI_ERR", "QUALITE_ERR", "LIVR_INCOMP",
        ),
    ),
    "suspended": StatusInfo(
        "Suspendue", "208", mdt88_code="39", manual_side="purchase", requires_detail=True,
        allowed_reasons=(
            "JUSTIF_ABS", "COORD_BANC_ERR", "CMD_ERR", "SIRET_ERR", "CODE_ROUTAGE_ERR",
            "REF_CT_ABSENT", "REF_ERR",
        ),
    ),
    "refused": StatusInfo(
        "Refusée",
        "210",
        mdt88_code="50",
        manual_side="purchase",
        requires_detail=True,
        requires_confirmation=True,
        # Liste "hors B2G" du schématron (BR-FR-CDV-CL-09_MDT-113_210) — la variante
        # B2G (émetteur GlobalID 0238 = "9999") a sa propre liste, non couverte ici
        # faute d'information B2G/B2B distincte dans notre modèle de données.
        allowed_reasons=(
            "TX_TVA_ERR", "MONTANTTOTAL_ERR", "CALCUL_ERR", "NON_CONFORME", "DOUBLON", "DEST_ERR",
            "TRANSAC_INC", "EMMET_INC", "CONTRAT_TERM", "DOUBLE_FACT", "CMD_ERR", "ADR_ERR",
            "REF_CT_ABSENT",
        ),
    ),
    # Statut métier saisissable manuellement (vente) — cf. note d'implémentation dans
    # LifecycleService : aucun point d'entrée IHM ne l'expose encore, faute d'écran de
    # suivi des factures émises (celles-ci ne sont pas stockées, § 4.1/§ 6.1).
    "completed": StatusInfo("Complétée", "209", mdt88_code="37", manual_side="sale"),
    # Statuts métier reçus uniquement (reflètent un fait déclaré par la contrepartie) —
    # volontairement non saisissables manuellement, cf. § 4.2.
    "payment_sent": StatusInfo("Paiement transmis", "211", mdt88_code="47"),
    "payment_received": StatusInfo("Encaissée", "212", mdt88_code="47"),
    # Autres statuts reçus/techniques.
    "rejected": StatusInfo("Rejetée", "213"),
    "stamped": StatusInfo("Visée", "214"),
    "cancelled": StatusInfo("Annulée", "220"),
    "routing_error": StatusInfo("Erreur de routage", "221"),
    "direct_payment_query": StatusInfo("Demande de paiement direct", "224"),
    "factored": StatusInfo("Affacturée", "225"),
    "undisclosed_factored": StatusInfo("Affacturée confidentiel", "226"),
    "payment_entity_change": StatusInfo("Changement de compte à payer", "227"),
    "not_factored": StatusInfo("Non affacturée", "228"),
    "unacceptable": StatusInfo("Irrecevable", "501"),
}

# Motifs (reason) utilisables sur les statuts qui en exigent un — sous-ensemble pertinent
# pour une saisie manuelle côté acheteur (la liste complète de la norme est bien plus
# longue et couvre aussi des rejets techniques hors périmètre de la saisie manuelle).
REASONS: dict[str, str] = {
    "NON_CONFORME": "Mention légale manquante",
    "SIRET_ERR": "SIRET erroné ou absent",
    "DOUBLON": "Facture en doublon (déjà émise / reçue)",
    "TX_TVA_ERR": "Taux de TVA erroné",
    "MONTANTTOTAL_ERR": "Montant total erroné",
    "CALCUL_ERR": "Erreur de calcul de la facture",
    "CMD_ERR": "N° de commande incorrect ou manquant",
    "PU_ERR": "Prix unitaires incorrects",
    "REM_ERR": "Remise erronée",
    "QTE_ERR": "Quantité facturée incorrecte",
    "ART_ERR": "Article facturé incorrect",
    "MODPAI_ERR": "Modalités de paiement incorrectes",
    "QUALITE_ERR": "Qualité d'article livré incorrecte",
    "LIVR_INCOMP": "Problème de livraison",
    "AUTRE": "Autre",
    "JUSTIF_ABS": "Justificatif absent",
    "CODE_ROUTAGE_ERR": "Code de routage erroné",
    "REF_CT_ABSENT": "Référence contractuelle absente",
    "REF_ERR": "Référence erronée",
    "COORD_BANC_ERR": "Coordonnées bancaires erronées",
    "DEST_INC": "Destinataire inconnu",
    "DEST_ERR": "Destinataire erroné",
    "TRANSAC_INC": "Transaction inconnue",
    "EMMET_INC": "Émetteur inconnu",
    "CONTRAT_TERM": "Contrat terminé",
    "DOUBLE_FACT": "Double facturation",
    "ADR_ERR": "Adresse erronée",
}

# Actions attendues (action) — cf. § 4.2.
ACTIONS: dict[str, str] = {
    "NOA": "Aucune action requise",
    "PIN": "Information complémentaire requise",
    "NIN": "Créer une facture rectificative",
    "CNF": "Créer un avoir total",
    "CNP": "Créer un avoir partiel",
    "CNA": "Rembourser le paiement de la facture",
    "OTH": "Autre",
}


def manual_statuses(side: ManualSide) -> list[str]:
    return [key for key, info in STATUS_CATALOG.items() if info.manual_side == side]
