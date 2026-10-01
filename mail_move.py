"""Outils IMAP pour retrouver un mail par son Message-ID et le déplacer d'un dossier à l'autre."""
import imaplib
import re

FOLDER_PREFIX = re.compile(r"INBOX[./](\d\d) - ")


def folder_map(imap: imaplib.IMAP4_SSL) -> dict[str, str]:
    """{'INBOX': 'INBOX', '00': 'INBOX/00 - ...', '01': ..., ...}"""
    folders = {"INBOX": "INBOX"}
    for line in imap.list()[1]:
        name = re.search(r'"([^"]+)"\s*$', line.decode())
        if name and (m := FOLDER_PREFIX.match(name.group(1))):
            folders[m.group(1)] = name.group(1)
    return folders


def _quote(name: str) -> str:
    return f'"{name}"'


def locate(imap: imaplib.IMAP4_SSL, message_id: str, folders: dict[str, str]) -> str | None:
    """Nom du dossier qui contient le mail, ou None."""
    for name in dict.fromkeys(folders.values()):
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
