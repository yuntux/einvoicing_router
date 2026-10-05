"""Backfill ponctuel : corrige les montants des factures UBL déjà ingérées avant le
correctif de `app/afnor/invoice_parsing.py` qui lisait le TTC sur `cbc:PayableAmount`
(le reste à payer) au lieu de `cbc:TaxInclusiveAmount` (le TTC réel) — sur une
facture déjà prélevée (ex. SEPA), `PayableAmount` tombe à 0 alors que le TTC ne
change pas.

Relit chaque fichier facture UBL déjà stocké sur disque, ré-exécute le parsing, et
met à jour `amount_total`/`amount_excl_tax`/`amount_tax` en base si le fichier donne
une valeur différente de celle enregistrée.

Dry-run par défaut (affiche les écarts sans rien écrire) — passer --apply pour
committer les changements.

Usage (depuis backend/, avec le même environnement que le service en production) :
    .venv/bin/python scripts/backfill_ubl_amount_total.py          # dry-run
    .venv/bin/python scripts/backfill_ubl_amount_total.py --apply  # applique
"""

import argparse
from pathlib import Path

from app.afnor.invoice_parsing import parse_invoice_fields
from app.db.session import SessionLocal
from app.models.invoicing import Invoice

_COMPARED_FIELDS = ("amount_total", "amount_excl_tax", "amount_tax")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Committer les changements (sinon dry-run).")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        invoices = db.query(Invoice).filter(Invoice.syntax == "UBL").all()
        print(f"{len(invoices)} facture(s) UBL en base.")

        changed = 0
        missing_file = 0
        for invoice in invoices:
            path = Path(invoice.file_path)
            if not path.is_file():
                missing_file += 1
                print(f"[ABSENT] facture #{invoice.id} ({invoice.invoice_number}) — fichier introuvable : {path}")
                continue

            parsed = parse_invoice_fields(path.read_bytes(), invoice.syntax)
            diffs = [
                (field, getattr(invoice, field), getattr(parsed, field))
                for field in _COMPARED_FIELDS
                if getattr(parsed, field) is not None and getattr(parsed, field) != getattr(invoice, field)
            ]
            if not diffs:
                continue

            changed += 1
            label = f"facture #{invoice.id} ({invoice.invoice_number}, {invoice.emitter_siren})"
            for field, old, new in diffs:
                print(f"[{'APPLIQUÉ' if args.apply else 'DIFF'}] {label} : {field} {old!r} -> {new!r}")
                if args.apply:
                    setattr(invoice, field, new)

        if args.apply and changed:
            db.commit()
            print(f"\n{changed} facture(s) corrigée(s) et committée(s).")
        elif changed:
            print(f"\n{changed} facture(s) à corriger (dry-run — relancer avec --apply pour écrire).")
        else:
            print("\nAucun écart détecté.")

        if missing_file:
            print(f"{missing_file} facture(s) UBL sans fichier retrouvé sur disque (ignorée(s)).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
