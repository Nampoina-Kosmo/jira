"""Détection des logos de signature : une image qui revient à l'identique dans plusieurs mails
différents est un logo récurrent, pas une pièce jointe utile. Une image unique n'est jamais écartée."""
import email
import hashlib
import imaplib
import json
import os

import state as st

HISTORY_FILE = st.STATE_FILE.with_name("image_hashes.json")
MIN_MAILS = int(os.getenv("LOGO_MIN_MAILS", "3"))  # vue dans au moins N AUTRES mails => logo
SEED_MAILS = 150  # mails de la boîte analysés au premier démarrage pour amorcer l'historique


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load() -> dict[str, list[str]]:
    if not HISTORY_FILE.exists() or not HISTORY_FILE.read_text().strip():
        return {}
    return json.loads(HISTORY_FILE.read_text())


def is_logo(image_hash: str, mail_id: str) -> bool:
    return len([m for m in _load().get(image_hash, []) if m != mail_id]) >= MIN_MAILS


def record(mail_id: str, hashes: set[str]) -> None:
    history = _load()
    for h in hashes:
        mails = history.setdefault(h, [])
        if mail_id not in mails:
            mails.append(mail_id)
    HISTORY_FILE.write_text(json.dumps(history))


def seed_if_needed(imap: imaplib.IMAP4_SSL) -> None:
    """Premier démarrage : apprend les logos récurrents à partir des derniers mails de la boîte."""
    if HISTORY_FILE.exists():
        return
    HISTORY_FILE.write_text("{}")
    imap.select("INBOX", readonly=True)
    nums = imap.search(None, "ALL")[1][0].split()[-SEED_MAILS:]
    for num in nums:
        msg = email.message_from_bytes(imap.fetch(num, "(BODY.PEEK[])")[1][0][1])
        hashes = {
            digest(p.get_payload(decode=True) or b"")
            for p in msg.walk()
            if p.get_content_maintype() == "image" and p.get_payload(decode=True)
        }
        if hashes:
            record(msg.get("Message-ID", f"no-id-{num.decode()}"), hashes)
    print(f"Historique des logos amorcé avec {len(nums)} mails")
