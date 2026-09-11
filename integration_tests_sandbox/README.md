# Suite d'intégration bac à sable SuperPDP

Suite pytest **séparée** de `backend/tests/` (spec.md § 10.4), qui appelle le vrai bac
à sable SuperPDP via `pyfrctc` — jamais exécutée par la CI bloquante (`ci.yml`), qui ne
doit jamais dépendre d'un service externe. Elle tourne uniquement dans le workflow
nightly non bloquant `.github/workflows/superpdp-sandbox-nightly.yml`.

## Identifiants requis

Ces variables d'environnement (GitHub Actions secrets en CI, `.env` local en dev) :

- `SUPERPDP_SANDBOX_CLIENT_ID`
- `SUPERPDP_SANDBOX_CLIENT_SECRET`
- `SUPERPDP_SANDBOX_COMPANY_SIREN`

Sans ces trois variables, **toute la suite est automatiquement passée en skip**
(`conftest.py`) — elle ne doit jamais faire échouer une exécution où les secrets ne
sont pas configurés (fork de PR, environnement de développeur sans accès sandbox...).

## Exécution locale

```bash
cd backend && . .venv/bin/activate  # réutilise l'environnement du backend (pyfrctc)
export SUPERPDP_SANDBOX_CLIENT_ID=...
export SUPERPDP_SANDBOX_CLIENT_SECRET=...
export SUPERPDP_SANDBOX_COMPANY_SIREN=...
cd ../integration_tests_sandbox
pytest -q
```

## Portée

- Connectivité (`healthcheck`), consultation d'annuaire sur un SIREN réel.
- Polling des factures reçues (`AfnorClientAdapter.get_client_for_company`).
- Ne couvre volontairement pas l'émission (pas de facture jetable à envoyer sans
  polluer un vrai flux SuperPDP) ni la génération/transmission CDAR réelle — ces
  parcours restent validés localement (XSD, sans réseau) par
  `backend/tests/unit/test_cdar_service.py`.
