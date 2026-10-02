"""Paramètres communs : mode dev/prod et destinataires de développement."""
import os

MODE = os.getenv("MODE", "prod").strip().lower()  # "dev" ou "prod"
if MODE not in ("dev", "prod"):
    raise SystemExit(f'MODE invalide : "{MODE}" (attendu : dev ou prod)')

# adresses qui reçoivent TOUS les mails envoyés par le système en mode dev (séparées par des virgules)
DEV_MAILS = [a.strip() for a in os.getenv("DEV_MAILS", "").split(",") if a.strip()]


# administrateurs prévenus à chaque création / changement de statut d'un ticket (dev et prod)
ADMIN_MAILS = [a.strip() for a in os.getenv("ADMIN_MAILS", "").split(",") if a.strip()]


def resolve_recipients(recipients: list[str]) -> list[str]:
    """Destinataires réels en prod ; en dev, les mails partent uniquement vers DEV_MAILS.
    Liste vide (ex. DEV_MAILS non renseigné en dev) = aucun mail envoyé."""
    return DEV_MAILS if MODE == "dev" else recipients
