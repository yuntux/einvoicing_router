# Contrats OpenAPI AFNOR (norme XP Z12-013)

Spécifications officielles de l'API AFNOR **consommée** par le routeur (rôle
**client**, via `pyfrctc` — cf. `app/afnor/client/pyfrctc_client.py`), fournies par
l'utilisateur et figées ici en v1.3.0 (juin 2026) :

- `afnor-flow-openapi-v1.3.0.json` — **AFNOR Flow Service** (`/afnor-flow`,
  ressource `/flows`) : soumission, recherche et téléchargement des flux
  (factures, cycles de vie CDAR, e-reporting). C'est ce schéma qui fait foi pour
  les champs réellement présents dans le Metadata d'un flux (`flowId`,
  `flowSyntax`, `processingRule`, `processingRuleSource`, `flowProfile`,
  `trackingId`, `flowDirection`, `flowType`, `acknowledgement`...) — **aucune
  donnée métier de facture** (émetteur, montants, numéro) n'y figure, cf.
  `app/afnor/invoice_parsing.py`.
- `afnor-directory-openapi-v1.3.0.json` — **AFNOR Directory Service**
  (`/afnor-directory`) : recherche/consultation SIREN, SIRET, codes de routage et
  lignes d'annuaire.

Ces fichiers documentent l'API **amont** (SuperPDP → routeur), distincte de l'API
que le routeur expose lui-même à Odoo (`app/api/afnor/v1.py`, § 4.4/§ 4.8), qui a
son propre design et n'est pas régie par ces contrats.

Ils servent de référence pour éviter que le mapping des champs dans
`app/afnor/client/pyfrctc_client.py`/`app/afnor/invoice_parsing.py` ne dérive de
suppositions non vérifiées — à terme, un test de contrat (cf. discussion) pourrait
comparer automatiquement les clés lues dans le code aux schémas déclarés ici.
