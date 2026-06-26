"""
Déchiffrement des anniversaires pour Home Assistant (pyscript).

Place ce fichier dans :  <config>/pyscript/anniversaires.py
Pré-requis (configuration.yaml) :
        pyscript:
          allow_all_imports: true
          calendar_key: !secret calendar_key
          anniversaires_url: !secret anniversaires_url
   et dans secrets.yaml :
        calendar_key: "TA_CLE_BASE64_DE_32_OCTETS"   # identique au secret GitHub
        anniversaires_url: "https://<pseudo>.github.io/anniversaires-calendar/anniversaires.ics"

Ce module :
  - expose un service  pyscript.anniversaires_refresh  qui télécharge l'ICS,
    déchiffre les titres et publie un capteur  sensor.anniversaires_a_venir
    (état = nombre dans les 30 jours, attribut "events" = liste détaillée) ;
  - rafraîchit automatiquement toutes les 6 heures.

La clé et l'URL ne sont JAMAIS écrites en dur ici : elles viennent de secrets.yaml.
"""

import base64
import datetime
import hmac
import hashlib
import urllib.request

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Config lue depuis le bloc `pyscript:` de configuration.yaml
CFG = pyscript.config


def decrypt_label(key: bytes, token: str) -> str:
    """Inverse exact de encrypt_label() côté générateur (AES-256-GCM)."""
    raw = base64.urlsafe_b64decode(token.encode("ascii"))
    nonce, ct = raw[:12], raw[12:]
    return AESGCM(key).decrypt(nonce, ct, None).decode("utf-8")


def _parse_ics(text: str):
    """Mini-parseur ICS : renvoie une liste de (date, summary)."""
    events, cur = [], {}
    # déplie les lignes (RFC 5545 : une ligne de continuation commence par espace)
    unfolded = text.replace("\r\n ", "").replace("\n ", "")
    for line in unfolded.splitlines():
        if line == "BEGIN:VEVENT":
            cur = {}
        elif line.startswith("DTSTART"):
            val = line.split(":", 1)[1].strip()
            cur["date"] = datetime.datetime.strptime(val[:8], "%Y%m%d").date()
        elif line.startswith("SUMMARY:"):
            cur["summary"] = line.split(":", 1)[1].strip()
        elif line == "END:VEVENT":
            if "date" in cur and "summary" in cur:
                events.append(cur)
    return events


@service
def anniversaires_refresh():
    """Service appelable : pyscript.anniversaires_refresh"""
    key = base64.urlsafe_b64decode(CFG["calendar_key"])
    url = CFG["anniversaires_url"]

    raw = task.executor(lambda: urllib.request.urlopen(url, timeout=30).read().decode("utf-8"))
    today = datetime.date.today()
    horizon = today + datetime.timedelta(days=30)

    upcoming = []
    for ev in _parse_ics(raw):
        summary = ev["summary"]
        if summary.startswith("🔒 "):
            try:
                label = decrypt_label(key, summary[2:].strip())
            except Exception:
                label = "(déchiffrement impossible)"
        else:
            label = summary.lstrip("🎂 ").strip()
        if today <= ev["date"] <= horizon:
            upcoming.append({
                "date": ev["date"].isoformat(),
                "in_days": (ev["date"] - today).days,
                "label": label,
            })

    upcoming.sort(key=lambda e: e["date"])
    state.set(
        "sensor.anniversaires_a_venir",
        value=len(upcoming),
        new_attributes={
            "unit_of_measurement": "anniv.",
            "icon": "mdi:cake-variant",
            "friendly_name": "Anniversaires à venir (30 j)",
            "events": upcoming,
        },
    )
    log.info(f"Anniversaires : {len(upcoming)} dans les 30 prochains jours")


@time_trigger("startup", "period(0:00, 6h)")
def anniversaires_auto():
    anniversaires_refresh()
