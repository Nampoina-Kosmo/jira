"""Outils IMAP pour retrouver un mail par son Message-ID et le déplacer d'un dossier à l'autre.

Les dossiers de statut portent le même nom que les statuts Jira et sont rangés sous INBOX :
INBOX/Idée, INBOX/Planifier, INBOX/En cours, INBOX/En revue, INBOX/Terminé.
Le statut « Nouvelle demande » correspond à INBOX lui-même.
"""
import base64
import imaplib
import re
from collections.abc import Iterable

STATUS_FOLDERS = ["Idée", "Planifier", "En cours", "En revue", "Terminé"]


def decode_utf7(name: str) -> str:
    """Décode un nom de dossier IMAP (UTF-7 modifié) : 'Termin&AOk-' -> 'Terminé'."""
    def repl(m: re.Match) -> str:
        if not m.group(1):
            return "&"
        b64 = m.group(1).replace(",", "/")
        return base64.b64decode(b64 + "=" * (-len(b64) % 4)).decode("utf-16-be")
    return re.sub(r"&([^-]*)-", repl, name)


def all_folders(imap: imaplib.IMAP4_SSL) -> dict[str, str]:
    """{nom décodé: nom brut IMAP} de tous les dossiers."""
    folders = {}
    for line in imap.list()[1]:
        name = re.search(r'"([^"]+)"\s*$', line.decode())
        if name:
            folders[decode_utf7(name.group(1))] = name.group(1)
    return folders


def folder_map(imap: imaplib.IMAP4_SSL) -> dict[str, str]:
    """{statut Jira: nom brut du dossier}. 'Nouvelle demande' -> INBOX ; un statut sans dossier est absent."""
    found = {decoded.split("/", 1)[1].casefold(): raw
             for decoded, raw in all_folders(imap).items() if decoded.startswith(("INBOX/", "INBOX."))}
    folders = {"Nouvelle demande": "INBOX"}
    for status in STATUS_FOLDERS:
        if status.casefold() in found:
            folders[status] = found[status.casefold()]
    return folders


def search_folders(imap: imaplib.IMAP4_SSL) -> list[str]:
    """Où chercher un mail : INBOX et tous ses sous-dossiers (y compris les anciens dossiers 00 à 04)."""
    return ["INBOX"] + [raw for decoded, raw in all_folders(imap).items() if decoded.startswith(("INBOX/", "INBOX."))]


def _quote(name: str) -> str:
    return f'"{name}"'


def locate(imap: imaplib.IMAP4_SSL, message_id: str, folders: Iterable[str]) -> str | None:
    """Nom du dossier qui contient le mail, ou None."""
    for name in dict.fromkeys(folders):
        imap.select(_quote(name), readonly=True)
        _, data = imap.uid("SEARCH", None, "HEADER", "Message-ID", _quote(message_id))
        if data[0]:
            return name
    return None


def move(imap: imaplib.IMAP4_SSL, message_id: str, src: str, dst: str) -> bool:
    """Copie le mail vers dst puis le supprime de src. Ne supprime rien si la copie échoue."""
    imap.select(_quote(src))
    _, data = imap.uid("SEARCH", None, "HEADER", "Message-ID", _quote(message_id))
    for uid in data[0].split():
        typ, _ = imap.uid("COPY", uid, _quote(dst))
        if typ != "OK":
            return False
        imap.uid("STORE", uid, "+FLAGS", "(\\Deleted)")
        if "UIDPLUS" in imap.capabilities:
            imap.uid("EXPUNGE", uid)  # n'efface que ce mail
        else:
            imap.expunge()
    return True
