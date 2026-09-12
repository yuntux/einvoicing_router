from app.models.referential import Company, PartnerDirectory, RoutingMethod, TargetApplication
from app.services import routing_rule_service


def _make_partner(db, siren="123456789"):
    partner = PartnerDirectory(siren=siren, name="Fournisseur Test")
    db.add(partner)
    db.commit()
    db.refresh(partner)
    return partner


def _make_company(db, siren="999999999", name="Ma Société"):
    company = Company(siren=siren, name=name)
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


def _make_target(db, company, name="Spendesk", routing_method=RoutingMethod.MAIL):
    target = TargetApplication(
        name=name,
        routing_method=routing_method,
        company_id=company.id,
        parameters={"to": ["a@b.com"]} if routing_method == RoutingMethod.MAIL else {},
    )
    db.add(target)
    db.commit()
    db.refresh(target)
    return target


def test_resolve_unknown_siren_returns_empty(db_session):
    result = routing_rule_service.resolve(db_session, siren="000000000")
    assert result == []


def test_resolve_no_rule_returns_empty(db_session):
    _make_partner(db_session)
    result = routing_rule_service.resolve(db_session, siren="123456789")
    assert result == []


def test_set_rule_active_true_creates_rule_and_resolve_finds_it(db_session):
    partner = _make_partner(db_session)
    company = _make_company(db_session)
    target = _make_target(db_session, company)
    routing_rule_service.set_rule_active(
        db_session,
        partner_directory_id=partner.id,
        target_application_id=target.id,
        active=True,
    )
    result = routing_rule_service.resolve(db_session, siren=partner.siren)
    assert [t.id for t in result] == [target.id]


def test_set_rule_active_false_removes_existing_rule(db_session):
    partner = _make_partner(db_session)
    company = _make_company(db_session)
    target = _make_target(db_session, company)
    routing_rule_service.set_rule_active(
        db_session, partner_directory_id=partner.id, target_application_id=target.id, active=True
    )
    routing_rule_service.set_rule_active(
        db_session, partner_directory_id=partner.id, target_application_id=target.id, active=False
    )
    result = routing_rule_service.resolve(db_session, siren=partner.siren)
    assert result == []


def test_set_rule_active_true_twice_is_idempotent(db_session):
    partner = _make_partner(db_session)
    company = _make_company(db_session)
    target = _make_target(db_session, company)
    routing_rule_service.set_rule_active(
        db_session, partner_directory_id=partner.id, target_application_id=target.id, active=True
    )
    routing_rule_service.set_rule_active(
        db_session, partner_directory_id=partner.id, target_application_id=target.id, active=True
    )
    rules = routing_rule_service.list_rules(db_session, partner_id=partner.id)
    assert len(rules) == 1


def test_resolve_multiple_targets(db_session):
    partner = _make_partner(db_session)
    company = _make_company(db_session)
    target_a = _make_target(db_session, company, name="Spendesk")
    target_b = _make_target(db_session, company, name="Comptable")
    routing_rule_service.set_rule_active(
        db_session, partner_directory_id=partner.id, target_application_id=target_a.id, active=True
    )
    routing_rule_service.set_rule_active(
        db_session, partner_directory_id=partner.id, target_application_id=target_b.id, active=True
    )
    result = routing_rule_service.resolve(db_session, siren=partner.siren)
    assert {t.id for t in result} == {target_a.id, target_b.id}


def test_resolve_excludes_afnor_api_target_of_another_company(db_session):
    """NF2 (cloisonnement strict) : un fournisseur commun aux deux entreprises ne doit
    jamais faire fuiter une facture de l'une vers l'application Odoo de l'autre."""
    company_a = _make_company(db_session, siren="111111111", name="Entreprise A")
    company_b = _make_company(db_session, siren="222222222", name="Entreprise B")
    partner = _make_partner(db_session)
    target_for_a = _make_target(
        db_session, company_a, name="Odoo A", routing_method=RoutingMethod.AFNOR_API
    )
    routing_rule_service.set_rule_active(
        db_session,
        partner_directory_id=partner.id,
        target_application_id=target_for_a.id,
        active=True,
    )

    result_for_b = routing_rule_service.resolve(
        db_session, siren=partner.siren, company_id=company_b.id
    )
    assert result_for_b == []

    result_for_a = routing_rule_service.resolve(
        db_session, siren=partner.siren, company_id=company_a.id
    )
    assert [t.id for t in result_for_a] == [target_for_a.id]


def test_resolve_excludes_mail_target_of_another_company(db_session):
    """Même règle que pour afnor_api (§ NF2) : une application mail est rattachée à
    une entreprise (`company_id` obligatoire) et n'est jamais retenue pour une facture
    reçue par une autre entreprise gérée, même si le fournisseur leur est commun."""
    company_a = _make_company(db_session, siren="111111111", name="Entreprise A")
    company_b = _make_company(db_session, siren="222222222", name="Entreprise B")
    partner = _make_partner(db_session)
    mail_target = _make_target(db_session, company_a, name="Spendesk")
    routing_rule_service.set_rule_active(
        db_session, partner_directory_id=partner.id, target_application_id=mail_target.id, active=True
    )

    result_for_b = routing_rule_service.resolve(
        db_session, siren=partner.siren, company_id=company_b.id
    )
    assert result_for_b == []

    result_for_a = routing_rule_service.resolve(
        db_session, siren=partner.siren, company_id=company_a.id
    )
    assert [t.id for t in result_for_a] == [mail_target.id]


def test_resolve_without_company_id_returns_all_targets(db_session):
    """`company_id=None` (prévisualisation admin) désactive le filtre par entreprise."""
    company_a = _make_company(db_session, siren="111111111", name="Entreprise A")
    partner = _make_partner(db_session)
    target_for_a = _make_target(
        db_session, company_a, name="Odoo A", routing_method=RoutingMethod.AFNOR_API
    )
    routing_rule_service.set_rule_active(
        db_session,
        partner_directory_id=partner.id,
        target_application_id=target_for_a.id,
        active=True,
    )

    result = routing_rule_service.resolve(db_session, siren=partner.siren)
    assert [t.id for t in result] == [target_for_a.id]
