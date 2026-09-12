"""Validation de la clé (Luhn) des identifiants SIREN/SIRET saisis dans l'IHM.

Un SIREN/SIRET bien formé (bonne longueur, uniquement des chiffres) peut tout de
même être une simple faute de frappe : la clé de contrôle Luhn qui le termine
permet de la détecter à la saisie plutôt qu'en aval (rejet SuperPDP, entrée
d'annuaire erronée, etc.). `python-stdnum` porte cette vérification pour éviter
de réimplémenter l'algorithme."""

from stdnum.fr import siren as siren_stdnum
from stdnum.fr import siret as siret_stdnum


def validate_siren(value: str) -> str:
    if not siren_stdnum.is_valid(value):
        raise ValueError("Numéro SIREN invalide (clé de contrôle incorrecte)")
    return value


def validate_siret(value: str) -> str:
    if not siret_stdnum.is_valid(value):
        raise ValueError("Numéro SIRET invalide (clé de contrôle incorrecte)")
    return value
