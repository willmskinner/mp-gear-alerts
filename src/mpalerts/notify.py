import os

import requests

RESEND_API_URL = "https://api.resend.com/emails"


def send_email(subject, html_body, text_body=None):
    payload = {
        "from": os.environ.get("FROM_EMAIL", "onboarding@resend.dev"),
        "to": [os.environ["NOTIFY_EMAIL"]],
        "subject": subject,
        "html": html_body,
    }
    if text_body:
        payload["text"] = text_body

    resp = requests.post(
        RESEND_API_URL,
        headers={"Authorization": f"Bearer {os.environ['RESEND_API_KEY']}"},
        json=payload,
        timeout=15,
    )
    if resp.status_code >= 300:
        raise RuntimeError(f"Resend API error {resp.status_code}: {resp.text}")
