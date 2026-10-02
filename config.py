"""Paramètres communs : mode dev/prod et destinataires de développement."""
import os

MODE = os.getenv("MODE", "prod").strip().lower()  # "dev" ou "prod"
if MODE not in ("dev", "prod"):
    raise SystemExit(f'MODE invalide : "{MODE}" (attendu : dev ou prod)')

# adresses qui reçoivent TOUS les mails envoyés par le système en mode dev (séparées par des virgules)
DEV_MAILS = [a.strip() for a in os.getenv("DEV_MAILS", "").split(",") if a.strip()]
if MODE == "dev" and not DEV_MAILS:
    raise SystemExit("MODE=dev : renseignez DEV_MAILS dans le .env (adresses séparées par des virgules)")


def resolve_recipients(recipients: list[str]) -> list[str]:
    """Destinataires réels en prod ; en dev, les mails partent uniquement vers DEV_MAILS."""
    return DEV_MAILS if MODE == "dev" else recipients
