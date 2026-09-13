"""`peppol_service.check_peppol_status` — résolution DNS PEPPOL indépendante de
SuperPDP (§ colonne "Annuaire Peppol" de la page de détail annuaire)."""

from unittest.mock import patch

from app.services.peppol_service import check_peppol_status


def test_active_participant_returns_access_point():
    with patch(
        "app.services.peppol_service.check_directory_line_peppol_status",
        return_value="ap.example.com",
    ):
        result = check_peppol_status("70204275500013")

    assert result == {"active": True, "access_point": "ap.example.com", "error": None}


def test_inactive_participant_returns_false_status():
    with patch(
        "app.services.peppol_service.check_directory_line_peppol_status",
        return_value=False,
    ):
        result = check_peppol_status("70204275500013")

    assert result == {"active": False, "access_point": None, "error": None}


def test_dns_error_is_reported_without_raising():
    with patch(
        "app.services.peppol_service.check_directory_line_peppol_status",
        side_effect=ValueError("DNS query could not be executed. Error: timeout"),
    ):
        result = check_peppol_status("70204275500013")

    assert result["active"] is False
    assert result["access_point"] is None
    assert "timeout" in result["error"]


def test_missing_identifier_does_not_call_dns():
    with patch(
        "app.services.peppol_service.check_directory_line_peppol_status"
    ) as mock_check:
        result = check_peppol_status(None)

    mock_check.assert_not_called()
    assert result["active"] is False
