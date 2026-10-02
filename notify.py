"""Mails envoyés au demandeur à chaque évolution de son ticket.

En mode dev, les mails partent uniquement vers DEV_MAILS (voir config.py) ; en prod, vers le demandeur.
Un mail est envoyé une seule fois par couple (ticket, statut) : le dernier statut notifié est mémorisé.
"""
import html
import json
import os
import smtplib
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

import config
import jira_api
import state as st

NOTIFIED_FILE = st.STATE_FILE.with_name("notified.json")
SIGNATURE = "Cordialement,\nL'équipe Support Signarama"

# statut Jira -> (objet, phrase d'introduction, phrase de conclusion)
TEMPLATES = {
    "Nouvelle demande": (
        "Votre demande a bien été enregistrée",
        "Nous avons bien reçu votre demande et vous remercions de nous l'avoir transmise. "
        "Un ticket a été créé afin d'en assurer le suivi.",
        "Nous reviendrons vers vous dès que son traitement évoluera.",
    ),
    "Idée": (
        "Votre demande est conservée comme idée d'amélioration",
        "Votre demande a été classée parmi nos idées d'amélioration. Elle est conservée et sera étudiée "
        "lors de la préparation de nos prochaines évolutions.",
        "Nous ne manquerons pas de vous informer si elle est retenue.",
    ),
    "Planifier": (
        "Votre demande a été prise en compte et planifiée",
        "Votre demande a été analysée et prise en compte. Elle est désormais planifiée dans notre organisation.",
        "Nous vous informerons dès le début de son traitement.",
    ),
    "En cours": (
        "Le traitement de votre demande a débuté",
        "Nous vous informons que le traitement de votre demande est en cours.",
        "Nous reviendrons vers vous dès qu'une nouvelle étape sera franchie.",
    ),
    "En revue": (
        "Votre demande est en cours de vérification",
        "Le traitement de votre demande est presque achevé : elle fait actuellement l'objet d'une dernière "
        "vérification avant sa clôture.",
        "Nous vous confirmerons sa finalisation très prochainement.",
    ),
    "Terminé": (
        "Votre demande a été traitée",
        "Nous avons le plaisir de vous informer que le traitement de votre demande est terminé.",
        "Si le résultat ne vous convenait pas ou si vous avez la moindre question, répondez simplement à ce "
        "message : nous reviendrons vers vous.",
    ),
}


def _load() -> dict[str, str]:
    if not NOTIFIED_FILE.exists() or not NOTIFIED_FILE.read_text().strip():
        return {}
    return json.loads(NOTIFIED_FILE.read_text())


def build_message(key: str, title: str, status: str, requester: str,
                  original_subject: str, original_id: str) -> EmailMessage:
    subject, intro, outro = TEMPLATES[status]
    link = f"{os.environ['JIRA_URL'].rstrip('/')}/browse/{key}"
    dev = config.MODE == "dev"
    recipients = config.resolve_recipients([requester])

    text = (
        f"Bonjour,\n\n{intro}\n\n"
        f"Référence : {key}\nObjet : {title}\nStatut : {status}\nSuivi du ticket : {link}\n\n"
        f"{outro}\n\n{SIGNATURE}\n"
    )
    body_html = (
        f"<p>Bonjour,</p><p>{html.escape(intro)}</p>"
        f"<table style='border-collapse:collapse'>"
        f"<tr><td style='padding:2px 12px 2px 0'><b>Référence</b></td><td>{html.escape(key)}</td></tr>"
        f"<tr><td style='padding:2px 12px 2px 0'><b>Objet</b></td><td>{html.escape(title)}</td></tr>"
        f"<tr><td style='padding:2px 12px 2px 0'><b>Statut</b></td><td>{html.escape(status)}</td></tr>"
        f"</table><p><a href='{html.escape(link)}'>Suivre le ticket {html.escape(key)}</a></p>"
        f"<p>{html.escape(outro)}</p><p>Cordialement,<br>L'équipe Support Signarama</p>"
    )
    if dev:  # rappel du destinataire réel pour faciliter les tests
        text = f"[MODE DEV] Destinataire réel en production : {requester}\n\n" + text
        body_html = f"<p style='color:#b45309'><i>[MODE DEV] Destinataire réel en production : {html.escape(requester)}</i></p>" + body_html

    msg = EmailMessage()
    msg["From"] = os.environ["MAIL_USER"]
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = f"{'[DEV] ' if dev else ''}[{key}] {subject}"
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=os.environ["MAIL_USER"].split("@")[-1])
    if original_id:  # le mail s'affiche dans la conversation d'origine du demandeur
        msg["In-Reply-To"] = original_id
        msg["References"] = original_id
    msg.set_content(text)
    msg.add_alternative(body_html, subtype="html")
    return msg


def build_admin_message(key: str, title: str, status: str, previous: str | None, requester: str) -> EmailMessage:
    """Mail d'information aux administrateurs : ticket créé ou changement de statut."""
    dev = config.MODE == "dev"
    link = f"{os.environ['JIRA_URL'].rstrip('/')}/browse/{key}"
    if previous is None:
        subject, what = f"[{key}] Nouveau ticket créé", "Un nouveau ticket vient d'être créé à partir d'un mail."
        change = f"Statut : {status}"
    else:
        subject, what = f"[{key}] Changement de statut : {status}", "Le statut d'un ticket vient d'évoluer."
        change = f"Statut : {previous} → {status}"
    requester_sent = ", ".join(config.resolve_recipients([requester])) or "aucun destinataire configuré"

    text = (
        f"Bonjour,\n\n{what}\n\nRéférence : {key}\nObjet : {title}\n{change}\nDemandeur : {requester}\n"
        f"Suivi du ticket : {link}\n\nLe demandeur a été informé par mail ({requester_sent}).\n\n"
        "Cordialement,\nNotification automatique Support Signarama\n"
    )
    body_html = (
        f"<p>Bonjour,</p><p>{html.escape(what)}</p>"
        f"<table style='border-collapse:collapse'>"
        f"<tr><td style='padding:2px 12px 2px 0'><b>Référence</b></td><td>{html.escape(key)}</td></tr>"
        f"<tr><td style='padding:2px 12px 2px 0'><b>Objet</b></td><td>{html.escape(title)}</td></tr>"
        f"<tr><td style='padding:2px 12px 2px 0'><b>{html.escape(change.split(' : ')[0])}</b></td>"
        f"<td>{html.escape(change.split(' : ', 1)[1])}</td></tr>"
        f"<tr><td style='padding:2px 12px 2px 0'><b>Demandeur</b></td><td>{html.escape(requester)}</td></tr>"
        f"</table><p><a href='{html.escape(link)}'>Ouvrir le ticket {html.escape(key)}</a></p>"
        f"<p>Le demandeur a été informé par mail ({html.escape(requester_sent)}).</p>"
        "<p>Cordialement,<br>Notification automatique Support Signarama</p>"
    )
    if dev:
        banner = f"[MODE DEV] Destinataire réel du mail au demandeur en production : {requester}"
        text = banner + "\n\n" + text
        body_html = f"<p style='color:#b45309'><i>{html.escape(banner)}</i></p>" + body_html

    msg = EmailMessage()
    msg["From"] = os.environ["MAIL_USER"]
    msg["To"] = ", ".join(config.ADMIN_MAILS)
    msg["Subject"] = f"{'[DEV] ' if dev else ''}{subject}"
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=os.environ["MAIL_USER"].split("@")[-1])
    msg.set_content(text)
    msg.add_alternative(body_html, subtype="html")
    return msg


def _send(msg: EmailMessage) -> None:
    with smtplib.SMTP_SSL(os.environ["SMTP_HOST"], int(os.environ["SMTP_PORT"])) as smtp:
        smtp.login(os.environ["MAIL_USER"], os.environ["MAIL_PASSWORD"])
        smtp.send_message(msg)


def sync(dry_run: bool) -> None:
    """Envoie un mail pour chaque ticket dont le statut a évolué depuis la dernière notification."""
    state = st.load()
    requesters = {}  # clé du ticket -> (demandeur, objet du mail d'origine, Message-ID d'origine)
    for mid, entry in state.items():
        if entry.get("issue_key") and entry.get("requester") and entry["issue_key"] not in requesters:
            requesters[entry["issue_key"]] = (entry["requester"], entry.get("subject", ""), mid)
    if not requesters:
        return

    notified = _load()
    issues = jira_api.get_issues(list(requesters))
    changed = False
    for key, (requester, subject, mid) in requesters.items():
        if key not in issues:
            continue
        status, title = issues[key]["status"], issues[key]["summary"]
        # 1er envoi : accusé de réception, puis éventuellement le statut atteint entre-temps
        last = notified.get(key)
        to_send = ["Nouvelle demande"] if last is None else []
        if status != (last or "Nouvelle demande"):
            to_send.append(status)
        for s in to_send:
            if s not in TEMPLATES:
                continue
            previous = notified.get(key) if key in notified else None  # None = création du ticket
            recipients = config.resolve_recipients([requester])
            print(f"Mail « {s} » pour {key} -> {', '.join(recipients) or 'aucun destinataire'}"
                  f" | admins : {', '.join(config.ADMIN_MAILS) or 'aucun'}")
            if dry_run:
                continue
            if recipients:
                try:
                    _send(build_message(key, title, s, requester, subject, mid))
                except Exception as exc:  # réessayé au prochain passage
                    print(f"Envoi échoué pour {key} : {exc!r}")
                    break
            notified[key] = s  # même sans destinataire : on ne renvoie pas l'évolution plus tard
            changed = True
            if config.ADMIN_MAILS:  # un échec ici ne doit pas renvoyer le mail au demandeur
                try:
                    _send(build_admin_message(key, title, s, previous, requester))
                except Exception as exc:
                    print(f"Mail admin échoué pour {key} : {exc!r}")
    if changed:
        NOTIFIED_FILE.write_text(json.dumps(notified, indent=2, ensure_ascii=False))
