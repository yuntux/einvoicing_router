from datetime import date

from app.models.referential import PartnerDirectory, RoutingMethod, TargetApplication
from app.services import routing_rule_service


def _make_partner(db, siren="123456789"):
    partner = PartnerDirectory(siren=siren, name="Fournisseur Test")
    db.add(partner)
    db.commit()
    db.refresh(partner)
    return partner


def _make_target(db, name="Spendesk"):
    target = TargetApplication(
        name=name, routing_method=RoutingMethod.MAIL, parameters={"to": ["a@b.com"]}
    )
    db.add(target)
    db.commit()
    db.refresh(target)
    return target


def test_resolve_unknown_siren_returns_empty(db_session):
    result = routing_rule_service.resolve(
        db_session, siren="000000000", reference_date=date(2026, 1, 1)
    )
    assert result == []


def test_resolve_no_rule_returns_empty(db_session):
    _make_partner(db_session)
    result = routing_rule_service.resolve(
        db_session, siren="123456789", reference_date=date(2026, 1, 1)
    )
    assert result == []


def test_resolve_active_rule_no_dates_matches_any_date(db_session):
    partner = _make_partner(db_session)
    target = _make_target(db_session)
    routing_rule_service.create_rule(
        db_session, partner_directory_id=partner.id, target_application_id=target.id
    )
    result = routing_rule_service.resolve(
        db_session, siren=partner.siren, reference_date=date(2099, 1, 1)
    )
    assert [t.id for t in result] == [target.id]


def test_resolve_respects_date_range(db_session):
    partner = _make_partner(db_session)
    target = _make_target(db_session)
    routing_rule_service.create_rule(
        db_session,
        partner_directory_id=partner.id,
        target_application_id=target.id,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )

    before = routing_rule_service.resolve(
        db_session, siren=partner.siren, reference_date=date(2025, 12, 31)
    )
    within = routing_rule_service.resolve(
        db_session, siren=partner.siren, reference_date=date(2026, 6, 1)
    )
    after = routing_rule_service.resolve(
        db_session, siren=partner.siren, reference_date=date(2027, 1, 1)
    )

    assert before == []
    assert [t.id for t in within] == [target.id]
    assert after == []


def test_resolve_ignores_inactive_rule(db_session):
    partner = _make_partner(db_session)
    target = _make_target(db_session)
    routing_rule_service.create_rule(
        db_session,
        partner_directory_id=partner.id,
        target_application_id=target.id,
        active=False,
    )
    result = routing_rule_service.resolve(
        db_session, siren=partner.siren, reference_date=date(2026, 1, 1)
    )
    assert result == []


def test_resolve_multiple_targets(db_session):
    partner = _make_partner(db_session)
    target_a = _make_target(db_session, name="Spendesk")
    target_b = _make_target(db_session, name="Comptable")
    routing_rule_service.create_rule(
        db_session, partner_directory_id=partner.id, target_application_id=target_a.id
    )
    routing_rule_service.create_rule(
        db_session, partner_directory_id=partner.id, target_application_id=target_b.id
    )
    result = routing_rule_service.resolve(
        db_session, siren=partner.siren, reference_date=date(2026, 1, 1)
    )
    assert {t.id for t in result} == {target_a.id, target_b.id}


def test_resolve_deduplicates_overlapping_rules_for_same_target(db_session):
    partner = _make_partner(db_session)
    target = _make_target(db_session)
    routing_rule_service.create_rule(
        db_session,
        partner_directory_id=partner.id,
        target_application_id=target.id,
        end_date=date(2026, 6, 30),
    )
    routing_rule_service.create_rule(
        db_session,
        partner_directory_id=partner.id,
        target_application_id=target.id,
        start_date=date(2026, 6, 1),
    )
    result = routing_rule_service.resolve(
        db_session, siren=partner.siren, reference_date=date(2026, 6, 15)
    )
    assert [t.id for t in result] == [target.id]
