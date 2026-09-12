"""RoutingRuleService — gestion et résolution des règles de routage (spec.md § 4.3, § 6.1)."""

from datetime import date

from sqlalchemy.orm import Session

from app.models.referential import PartnerDirectory, RoutingRule, TargetApplication


def list_rules(db: Session, *, partner_id: int | None = None) -> list[RoutingRule]:
    query = db.query(RoutingRule)
    if partner_id is not None:
        query = query.filter(RoutingRule.partner_directory_id == partner_id)
    return list(query.order_by(RoutingRule.id).all())


def create_rule(
    db: Session,
    *,
    partner_directory_id: int,
    target_application_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
    active: bool = True,
) -> RoutingRule:
    rule = RoutingRule(
        partner_directory_id=partner_directory_id,
        target_application_id=target_application_id,
        start_date=start_date,
        end_date=end_date,
        active=active,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def upsert_rule(
    db: Session,
    *,
    partner_directory_id: int,
    target_application_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
) -> RoutingRule:
    """Crée ou met à jour la règle du couple (fournisseur, application cible) — chaque
    cellule de la matrice de la page Règles de routage est éditable directement,
    qu'une règle existe déjà ou non pour ce couple (§ 4.3)."""
    rule = (
        db.query(RoutingRule)
        .filter(
            RoutingRule.partner_directory_id == partner_directory_id,
            RoutingRule.target_application_id == target_application_id,
        )
        .first()
    )
    if rule is None:
        rule = RoutingRule(
            partner_directory_id=partner_directory_id,
            target_application_id=target_application_id,
        )
        db.add(rule)
    rule.start_date = start_date
    rule.end_date = end_date
    db.commit()
    db.refresh(rule)
    return rule


def resolve(
    db: Session, *, siren: str, reference_date: date, company_id: int | None = None
) -> list[TargetApplication]:
    """Résout les applications cibles pour un émetteur (SIREN) et une date de référence
    donnés (typiquement la date de réception d'une facture, § 4.3).

    Retourne 0, 1 ou N `TargetApplication` — celles dont une `RoutingRule` active couvre
    `reference_date` pour cet émetteur. Si l'émetteur n'a pas d'entrée `PartnerDirectory`,
    retourne une liste vide (cf. spec.md § 6.1, note sur l'alerte "facture non routée").

    `company_id` (l'entreprise réceptrice de la facture, § 4.10/NF2) exclut les
    applications cibles (mail comme afnor_api, `TargetApplication.company_id` est
    obligatoire) rattachées à une **autre** entreprise gérée — sans ce filtre, un même
    fournisseur facturant les deux entreprises gérées ferait fuiter une facture de
    l'une vers l'application de l'autre (§ NF2 : cloisonnement strict). Laisser
    `company_id=None` (ex. prévisualisation admin) désactive ce filtre et retourne
    toutes les cibles possibles, tous rattachements confondus.
    """
    partner = db.query(PartnerDirectory).filter(PartnerDirectory.siren == siren).first()
    if partner is None:
        return []

    rules = (
        db.query(RoutingRule)
        .filter(
            RoutingRule.partner_directory_id == partner.id,
            RoutingRule.active.is_(True),
        )
        .all()
    )

    matching = [
        rule
        for rule in rules
        if (rule.start_date is None or rule.start_date <= reference_date)
        and (rule.end_date is None or rule.end_date >= reference_date)
    ]

    # Une même application cible ne doit apparaître qu'une fois même si plusieurs règles
    # actives la couvrent (ex. chevauchement volontaire lors d'une transition de règles).
    seen: set[int] = set()
    targets: list[TargetApplication] = []
    for rule in matching:
        target = rule.target_application
        if target.id in seen or not target.is_active:
            continue
        if company_id is not None and target.company_id != company_id:
            continue
        seen.add(target.id)
        targets.append(target)
    return targets
