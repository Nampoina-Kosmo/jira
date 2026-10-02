"""Synchronise le statut des tickets Jira avec le dossier IMAP dans lequel le mail est rangé."""
import email
import imaplib
import os
import re

import jira_api
import state as st

# préfixe du nom de dossier -> statut Jira (le dossier 04 n'a volontairement aucune action)
FOLDER_STATUS = {
    "00": "Planifier",   # 00 - Message Pris en Compte
    "01": "En cours",    # 01 - A traiter par Wiem
    "02": "En cours",    # 02 - A traiter par Philippe
    "03": "Terminé",     # 03 - Traitement terminé
    "04": "Idée",        # 04 - Idées améliorations à conserver
}


def _watched_folders(imap: imaplib.IMAP4_SSL) -> dict[str, str]:
    folders = {}
    for line in imap.list()[1]:
        name = re.search(r'"([^"]+)"\s*$', line.decode())
        if not name:
            continue
        name = name.group(1)
        m = re.match(r"INBOX[./](\d\d) - ", name)
        if m and m.group(1) in FOLDER_STATUS:
            folders[name] = FOLDER_STATUS[m.group(1)]
    return folders


def _headers(imap: imaplib.IMAP4_SSL) -> list[tuple[str, list[str]]]:
    """(Message-ID, [ids cités dans In-Reply-To/References]) de tous les mails du dossier courant."""
    _, data = imap.fetch("1:*", "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID IN-REPLY-TO REFERENCES)])")
    out = []
    for item in data:
        if not isinstance(item, tuple):
            continue
        msg = email.message_from_bytes(item[1])
        mid = (msg.get("Message-ID") or "").strip()
        refs = re.findall(r"<[^>]+>", f"{msg.get('In-Reply-To', '')} {msg.get('References', '')}")
        if mid:
            out.append((mid, refs[::-1]))  # le plus récent d'abord
    return out


def sync(dry_run: bool) -> None:
    state = st.load()
    changed = False
    with imaplib.IMAP4_SSL(os.environ["IMAP_HOST"], int(os.environ["IMAP_PORT"])) as imap:
        imap.login(os.environ["MAIL_USER"], os.environ["MAIL_PASSWORD"])
        for folder, status in _watched_folders(imap).items():
            _, count = imap.select(f'"{folder}"', readonly=True)
            if not int(count[0] or 0):
                continue
            for mid, refs in _headers(imap):
                entry = state.get(mid)
                if entry and entry.get("status") == status:
                    continue  # déjà appliqué
                # ticket du mail lui-même, sinon de la conversation à laquelle il répond
                key = (entry or {}).get("issue_key") or next(
                    (state[r]["issue_key"] for r in refs if state.get(r, {}).get("issue_key")), None
                )
                if not key:
                    continue
                print(f"[{folder}] {mid} -> {key} : {status}")
                if dry_run:
                    continue
                try:
                    jira_api.transition_issue(key, status)
                except Exception as exc:  # réessayé au prochain passage
                    print(f"Transition échouée pour {key} : {exc!r}")
                    continue
                state[mid] = {"issue_key": key, "status": status}
                changed = True
    if changed:
        st.save(state)
