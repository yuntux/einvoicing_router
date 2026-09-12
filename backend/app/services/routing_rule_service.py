"""RoutingRuleService — gestion et résolution des règles de routage (spec.md § 4.3, § 6.1).

Une `RoutingRule` n'a ni période de validité ni drapeau `active` : son existence même
signifie que le routage est actif pour ce couple (fournisseur, application cible)."""

from sqlalchemy.orm import Session

from app.models.referential import PartnerDirectory, RoutingRule, TargetApplication


def list_rules(db: Session, *, partner_id: int | None = None) -> list[RoutingRule]:
    query = db.query(RoutingRule)
    if partner_id is not None:
        query = query.filter(RoutingRule.partner_directory_id == partner_id)
    return list(query.order_by(RoutingRule.id).all())


def get_rule(
    db: Session, *, partner_directory_id: int, target_application_id: int
) -> RoutingRule | None:
    return (
        db.query(RoutingRule)
        .filter(
            RoutingRule.partner_directory_id == partner_directory_id,
            RoutingRule.target_application_id == target_application_id,
        )
        .first()
    )


def set_rule_active(
    db: Session,
    *,
    partner_directory_id: int,
    target_application_id: int,
    active: bool,
    actor_user_id: int | None = None,
) -> RoutingRule | None:
    """Coche/décoche la case (fournisseur, application cible) de la matrice IHM
    (§ 4.3) : `active=True` crée la ligne si absente, `active=False` la supprime si
    présente. Renvoie la règle (créée ou déjà existante), ou `None` après suppression."""
    rule = get_rule(
        db, partner_directory_id=partner_directory_id, target_application_id=target_application_id
    )
    if active:
        if rule is None:
            rule = RoutingRule(
                partner_directory_id=partner_directory_id,
                target_application_id=target_application_id,
                create_user_id=actor_user_id,
                write_user_id=actor_user_id,
            )
            db.add(rule)
            db.commit()
            db.refresh(rule)
        return rule

    if rule is not None:
        db.delete(rule)
        db.commit()
    return None


def resolve(
    db: Session, *, siren: str, company_id: int | None = None
) -> list[TargetApplication]:
    """Résout les applications cibles pour un émetteur (SIREN) donné (§ 4.3).

    Retourne 0, 1 ou N `TargetApplication` — celles pour lesquelles une `RoutingRule`
    existe pour cet émetteur. Si l'émetteur n'a pas d'entrée `PartnerDirectory`,
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

    rules = db.query(RoutingRule).filter(RoutingRule.partner_directory_id == partner.id).all()

    # Une même application cible ne doit apparaître qu'une fois même si plusieurs
    # règles la couvrent (ne devrait plus arriver avec la contrainte d'unicité du
    # couple, gardé par prudence).
    seen: set[int] = set()
    targets: list[TargetApplication] = []
    for rule in rules:
        target = rule.target_application
        if target.id in seen or not target.is_active:
            continue
        if company_id is not None and target.company_id != company_id:
            continue
        seen.add(target.id)
        targets.append(target)
    return targets
