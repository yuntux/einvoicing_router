from datetime import date
from pathlib import Path

from app.afnor.client.base import RawInvoice
from app.afnor.client.fake import FakeSuperPDPClient
from app.models.invoicing import Invoice
from app.models.referential import Company, PartnerDirectory, RoutingMethod, TargetApplication
from app.services import invoice_ingestion_service, retry_scheduler_service, routing_rule_service
from app.services.invoice_ingestion_service import ingest_from_client


def _make_company(db, siren="111111111"):
    company = Company(siren=siren, name="Ma Société")
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


def _raw_invoice(**overrides):
    defaults = dict(
        superpdp_flow_id="flow-1",
        emitter_siren="222222222",
        invoice_number="F-2026-001",
        invoice_date=date(2026, 1, 15),
        file_name="F-2026-001.pdf",
        file_content=b"%PDF-fake-content",
    )
    defaults.update(overrides)
    return RawInvoice(**defaults)


def test_ingest_stores_file_and_creates_invoice(db_session, tmp_path):
    company = _make_company(db_session)
    client = FakeSuperPDPClient([_raw_invoice()])

    result = ingest_from_client(db_session, company=company, client=client)

    assert len(result.created) == 1
    invoice = result.created[0]
    assert invoice.emitter_siren == "222222222"
    assert invoice.invoice_number == "F-2026-001"
    assert invoice.superpdp_flow_id == "flow-1"
    assert Path(invoice.file_path).exists()
    assert Path(invoice.file_path).read_bytes() == b"%PDF-fake-content"


def test_ingest_is_idempotent_on_flow_id(db_session):
    company = _make_company(db_session)
    client = FakeSuperPDPClient([_raw_invoice()])

    first = ingest_from_client(db_session, company=company, client=client)
    second = ingest_from_client(db_session, company=company, client=client)

    assert len(first.created) == 1
    assert len(second.created) == 0
    assert len(second.updated) == 1
    assert first.created[0].id == second.updated[0].id


def test_ingest_flags_invoice_with_no_routing_rule(db_session):
    company = _make_company(db_session)
    client = FakeSuperPDPClient([_raw_invoice()])

    result = ingest_from_client(db_session, company=company, client=client)

    assert result.unrouted_invoice_ids == [result.created[0].id]
    assert result.created[0].routings == []


def test_ingest_from_unknown_supplier_creates_partner_and_alerts_once(db_session, monkeypatch):
    """§ 4.4/§ 4.7 : la première facture d'un fournisseur jamais vu jusque-là crée
    automatiquement son entrée d'annuaire (nom placeholder, pas de lookup SIRENE) et
    déclenche l'alerte dédiée "nouveau fournisseur sans règle de routage" — pas
    l'alerte générique "facture non routée", qui resterait moins actionnable ici."""
    new_partner_calls = []
    unrouted_calls = []
    monkeypatch.setattr(
        retry_scheduler_service,
        "alert_new_partner_without_routing_rule",
        lambda db, *, partner, sender=None: new_partner_calls.append(partner.siren),
    )
    monkeypatch.setattr(
        retry_scheduler_service,
        "alert_unrouted_invoice",
        lambda db, *, invoice, sender=None: unrouted_calls.append(invoice.id),
    )

    company = _make_company(db_session)
    client = FakeSuperPDPClient([_raw_invoice(emitter_siren="222222222")])
    result = ingest_from_client(db_session, company=company, client=client)

    partner = (
        db_session.query(PartnerDirectory).filter(PartnerDirectory.siren == "222222222").first()
    )
    assert partner is not None
    assert result.created[0].partner_directory_id == partner.id
    assert new_partner_calls == ["222222222"]
    assert unrouted_calls == []


def test_ingest_uses_emitter_name_from_flow_when_available(db_session):
    """§ 4.4 : quand le flux AFNOR porte la raison sociale de l'émetteur, elle est
    utilisée directement plutôt que le placeholder générique."""
    company = _make_company(db_session)
    client = FakeSuperPDPClient(
        [_raw_invoice(emitter_siren="222222222", emitter_name="Fournisseur Réel SAS")]
    )
    ingest_from_client(db_session, company=company, client=client)

    partner = (
        db_session.query(PartnerDirectory).filter(PartnerDirectory.siren == "222222222").first()
    )
    assert partner.name == "Fournisseur Réel SAS"


def test_ingest_backfills_placeholder_partner_name_once_available(db_session):
    """Un fournisseur déjà auto-créé avec le placeholder générique (première facture
    sans nom exploitable) doit être complété rétroactivement dès qu'un nom finit par
    arriver sur une facture suivante — plutôt que de rester générique indéfiniment."""
    company = _make_company(db_session)
    ingest_from_client(
        db_session, company=company, client=FakeSuperPDPClient([_raw_invoice(emitter_siren="222222222")])
    )
    partner = (
        db_session.query(PartnerDirectory).filter(PartnerDirectory.siren == "222222222").first()
    )
    assert partner.name == "Fournisseur 222222222 (à compléter)"

    ingest_from_client(
        db_session,
        company=company,
        client=FakeSuperPDPClient(
            [
                _raw_invoice(
                    superpdp_flow_id="flow-2",
                    emitter_siren="222222222",
                    emitter_name="Fournisseur Réel SAS",
                )
            ]
        ),
    )
    db_session.refresh(partner)
    assert partner.name == "Fournisseur Réel SAS"


def test_ingest_does_not_repeat_generic_unrouted_alert_on_next_poll(db_session, monkeypatch):
    """Une fois l'annuaire renseigné (fournisseur déjà connu, toujours sans règle),
    l'alerte générique "facture non routée" ne doit partir qu'une fois par facture —
    jamais rejouée à chaque cycle de polling (§ 4.7)."""
    unrouted_calls = []
    monkeypatch.setattr(
        retry_scheduler_service,
        "alert_unrouted_invoice",
        lambda db, *, invoice, sender=None: unrouted_calls.append(invoice.id),
    )

    company = _make_company(db_session)
    partner = PartnerDirectory(siren="222222222", name="Fournisseur déjà connu")
    db_session.add(partner)
    db_session.commit()

    raw = _raw_invoice()
    ingest_from_client(db_session, company=company, client=FakeSuperPDPClient([raw]))
    assert len(unrouted_calls) == 1

    # Même flux re-scanné (ex. avant que le curseur de polling n'avance) : toujours
    # aucune cible, mais l'alerte ne doit pas repartir une seconde fois.
    ingest_from_client(db_session, company=company, client=FakeSuperPDPClient([raw]))
    assert len(unrouted_calls) == 1


def test_reroute_unrouted_invoices_for_partner_after_rule_added(db_session):
    """Ajouter une règle de routage pour un fournisseur doit immédiatement router ses
    factures déjà reçues et restées sans cible, sans attendre le prochain polling."""
    company = _make_company(db_session)
    client = FakeSuperPDPClient([_raw_invoice(emitter_siren="222222222")])
    result = ingest_from_client(db_session, company=company, client=client)
    invoice = result.created[0]
    assert invoice.routings == []

    partner = (
        db_session.query(PartnerDirectory).filter(PartnerDirectory.siren == "222222222").first()
    )
    target = TargetApplication(
        name="Spendesk",
        routing_method=RoutingMethod.MAIL,
        company_id=company.id,
        parameters={"to": ["a@b.com"]},
    )
    db_session.add(target)
    db_session.commit()
    db_session.refresh(target)
    routing_rule_service.set_rule_active(
        db_session, partner_directory_id=partner.id, target_application_id=target.id, active=True
    )

    rerouted = invoice_ingestion_service.reroute_unrouted_invoices_for_partner(
        db_session, partner_directory_id=partner.id, target_application_id=target.id
    )

    assert rerouted == 1
    db_session.refresh(invoice)
    assert [r.target_application_id for r in invoice.routings] == [target.id]


def test_reroute_unrouted_invoices_for_partner_fans_out_to_second_target(db_session):
    """Activer un 2e canal pour un fournisseur qui en a déjà un ne doit pas ignorer
    les factures déjà routées vers le premier : elle doivent recevoir un routage
    supplémentaire vers le nouveau canal, sans dupliquer celui déjà en place."""
    company = _make_company(db_session)
    client = FakeSuperPDPClient([_raw_invoice(emitter_siren="222222222")])
    result = ingest_from_client(db_session, company=company, client=client)
    invoice = result.created[0]

    partner = (
        db_session.query(PartnerDirectory).filter(PartnerDirectory.siren == "222222222").first()
    )
    target_a = TargetApplication(
        name="Canal A",
        routing_method=RoutingMethod.MAIL,
        company_id=company.id,
        parameters={"to": ["a@b.com"]},
    )
    target_b = TargetApplication(
        name="Canal B",
        routing_method=RoutingMethod.MAIL,
        company_id=company.id,
        parameters={"to": ["c@d.com"]},
    )
    db_session.add_all([target_a, target_b])
    db_session.commit()
    db_session.refresh(target_a)
    db_session.refresh(target_b)

    routing_rule_service.set_rule_active(
        db_session, partner_directory_id=partner.id, target_application_id=target_a.id, active=True
    )
    invoice_ingestion_service.reroute_unrouted_invoices_for_partner(
        db_session, partner_directory_id=partner.id, target_application_id=target_a.id
    )

    routing_rule_service.set_rule_active(
        db_session, partner_directory_id=partner.id, target_application_id=target_b.id, active=True
    )
    rerouted = invoice_ingestion_service.reroute_unrouted_invoices_for_partner(
        db_session, partner_directory_id=partner.id, target_application_id=target_b.id
    )

    assert rerouted == 1
    db_session.refresh(invoice)
    assert {r.target_application_id for r in invoice.routings} == {target_a.id, target_b.id}


def test_ingest_creates_routing_when_rule_matches(db_session):
    company = _make_company(db_session)

    partner = PartnerDirectory(siren="222222222", name="Fournisseur")
    db_session.add(partner)
    target = TargetApplication(
        name="Spendesk",
        routing_method=RoutingMethod.MAIL,
        company_id=company.id,
        parameters={"to": ["a@b.com"]},
    )
    db_session.add(target)
    db_session.commit()
    db_session.refresh(partner)
    db_session.refresh(target)
    routing_rule_service.set_rule_active(
        db_session,
        partner_directory_id=partner.id,
        target_application_id=target.id,
        active=True,
    )

    client = FakeSuperPDPClient([_raw_invoice()])
    result = ingest_from_client(db_session, company=company, client=client)

    assert result.unrouted_invoice_ids == []
    invoice = result.created[0]
    assert len(invoice.routings) == 1
    assert invoice.routings[0].target_application_id == target.id
    assert invoice.routings[0].transfer_status == "to_send"


def test_ingest_does_not_leak_invoice_to_other_company_afnor_target(db_session):
    """NF2 : un fournisseur commun aux deux entreprises gérées ne doit jamais faire
    router une facture reçue par l'une vers l'application Odoo (afnor_api) de
    l'autre — seule la cible de l'entreprise réceptrice réelle est retenue."""
    company_a = _make_company(db_session, siren="111111111")
    company_b = _make_company(db_session, siren="333333333")

    partner = PartnerDirectory(siren="222222222", name="Fournisseur Commun")
    db_session.add(partner)
    target_a = TargetApplication(
        name="Odoo A", routing_method=RoutingMethod.AFNOR_API, company_id=company_a.id
    )
    db_session.add(target_a)
    db_session.commit()
    db_session.refresh(partner)
    db_session.refresh(target_a)
    routing_rule_service.set_rule_active(
        db_session,
        partner_directory_id=partner.id,
        target_application_id=target_a.id,
        active=True,
    )

    # Le même fournisseur envoie aussi une facture à l'entreprise B.
    client_b = FakeSuperPDPClient([_raw_invoice(superpdp_flow_id="flow-b")])
    result_b = ingest_from_client(db_session, company=company_b, client=client_b)

    invoice_b = result_b.created[0]
    assert invoice_b.routings == []
    assert result_b.unrouted_invoice_ids == [invoice_b.id]

    # La facture reçue par l'entreprise A, elle, doit toujours être routée normalement.
    client_a = FakeSuperPDPClient([_raw_invoice(superpdp_flow_id="flow-a")])
    result_a = ingest_from_client(db_session, company=company_a, client=client_a)

    invoice_a = result_a.created[0]
    assert [r.target_application_id for r in invoice_a.routings] == [target_a.id]
