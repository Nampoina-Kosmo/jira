"""Jira -> mail : quand le statut d'un ticket change dans Jira, le mail associé est rangé
dans le dossier du même nom (INBOX pour « Nouvelle demande »)."""
import imaplib
import os

import jira_api
import mail_move
import state as st


def sync(dry_run: bool) -> None:
    state = st.load()
    unknown = {e["issue_key"] for e in state.values() if e.get("issue_key") and not e.get("status")}
    if unknown:  # tickets créés avant le suivi des statuts : on mémorise leur statut actuel
        current = jira_api.get_statuses(sorted(unknown))
        for entry in state.values():
            if entry.get("issue_key") in current and not entry.get("status"):
                entry["status"] = current[entry["issue_key"]]
        if not dry_run:
            st.save(state)
    by_ticket: dict[str, list[str]] = {}
    for mid, entry in state.items():
        if entry.get("issue_key") and entry.get("status"):
            by_ticket.setdefault(entry["issue_key"], []).append(mid)
    if not by_ticket:
        return

    statuses = jira_api.get_statuses(list(by_ticket))
    pending = [
        (key, mid, statuses[key])
        for key, mids in by_ticket.items() if key in statuses
        for mid in mids if state[mid]["status"] != statuses[key]
    ]
    if not pending:
        return

    changed = False
    with imaplib.IMAP4_SSL(os.environ["IMAP_HOST"], int(os.environ["IMAP_PORT"])) as imap:
        imap.login(os.environ["MAIL_USER"], os.environ["MAIL_PASSWORD"])
        folders = mail_move.folder_map(imap)      # {statut: dossier}
        searchable = mail_move.search_folders(imap)
        for key, mid, status in pending:
            dst = folders.get(status)
            if dst is None:  # statut sans dossier : on mémorise seulement le nouveau statut
                state[mid]["status"] = status
                changed = True
                continue
            src = mail_move.locate(imap, mid, searchable)
            if src is None:
                print(f"{key} : mail {mid} introuvable, ignoré")
                state[mid]["status"] = status
                changed = True
                continue
            if src != dst:
                print(f"{key} -> {status} : mail {mid} déplacé de « {mail_move.decode_utf7(src)} » "
                      f"vers « {mail_move.decode_utf7(dst)} »")
                if dry_run:
                    continue
                try:
                    if not mail_move.move(imap, mid, src, dst):
                        print("Copie refusée, réessai au prochain passage")
                        continue
                except Exception as exc:
                    print(f"Déplacement échoué pour {mid} : {exc!r}")
                    continue
            state[mid]["status"] = status
            changed = True
    if changed and not dry_run:
        st.save(state)
