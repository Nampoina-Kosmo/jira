"""Mail -> Jira : le statut du ticket suit le dossier IMAP dans lequel le mail est rangé.

Dossiers surveillés (même nom que le statut Jira, sous INBOX) :
Idée, Planifier, En cours, En revue, Terminé.
"""
import email
import imaplib
import os
import re

import jira_api
import mail_move
import state as st


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
        watched = {raw: status for status, raw in mail_move.folder_map(imap).items() if raw != "INBOX"}
        for folder, status in watched.items():
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
                print(f"[{mail_move.decode_utf7(folder)}] {mid} -> {key} : {status}")
                if dry_run:
                    continue
                try:
                    jira_api.transition_issue(key, status)
                except Exception as exc:  # réessayé au prochain passage
                    print(f"Transition échouée pour {key} : {exc!r}")
                    continue
                state.setdefault(mid, {}).update(issue_key=key, status=status)  # garde demandeur et objet
                changed = True
    if changed:
        st.save(state)
