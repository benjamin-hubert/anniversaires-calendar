#!/usr/bin/env python3
"""
Génère un fichier .ics (iCalendar) d'anniversaires à partir d'un contacts.json.

Pour chaque personne, on crée un événement journée entière par année, avec
l'âge calculé inscrit dans le titre :  "🎂 Marie Dupont (33 ans)".

Le format ICS ne sait pas calculer l'âge tout seul : on génère donc une
occurrence par année sur une fenêtre glissante. L'action GitHub régénère le
fichier régulièrement pour que la fenêtre reste à jour.

Confidentialité : si la variable d'environnement CALENDAR_KEY est définie (clé
base64 de 32 octets), le titre de chaque événement (prénom + âge) est chiffré en
AES-256-GCM déterministe. Le fichier publié ne contient alors aucun prénom en
clair ; seul Home Assistant, avec la même clé, peut les déchiffrer.

Usage :
    python generate.py [--years 80] [--input data/contacts.json] [--output public/anniversaires.ics]
"""

import argparse
import base64
import datetime as dt
import hashlib
import hmac
import json
import os
from pathlib import Path

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:  # chiffrement indisponible sans le module cryptography
    AESGCM = None


def load_key() -> bytes | None:
    """Charge la clé depuis CALENDAR_KEY (base64 de 32 octets), ou None."""
    raw = os.environ.get("CALENDAR_KEY", "").strip()
    if not raw:
        return None
    if AESGCM is None:
        raise SystemExit("CALENDAR_KEY défini mais le module 'cryptography' est absent.")
    try:
        key = base64.urlsafe_b64decode(raw)
    except Exception as exc:
        raise SystemExit(f"CALENDAR_KEY illisible (base64 attendu) : {exc}")
    if len(key) != 32:
        raise SystemExit("CALENDAR_KEY doit décoder vers 32 octets (AES-256).")
    return key


def encrypt_label(key: bytes, plaintext: str) -> str:
    """Chiffrement AES-256-GCM déterministe → jeton base64 urlsafe.

    Le nonce est dérivé du texte clair (HMAC-SHA256) : un même texte donne
    toujours le même jeton, ce qui évite de réécrire tout le fichier à chaque
    build. Côté Home Assistant, un simple AESGCM().decrypt() suffit.
    """
    data = plaintext.encode("utf-8")
    nonce = hmac.new(key, data, hashlib.sha256).digest()[:12]
    ct = AESGCM(key).encrypt(nonce, data, None)
    return base64.urlsafe_b64encode(nonce + ct).decode("ascii")


def fold(line: str) -> str:
    """Plie les lignes à 75 octets, comme l'exige la RFC 5545."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    chunks = []
    while len(raw) > 75:
        # On coupe sur une frontière de caractère (utf-8 safe).
        cut = 75
        while (raw[cut] & 0xC0) == 0x80:  # ne pas couper au milieu d'un caractère
            cut -= 1
        chunks.append(raw[:cut])
        raw = b" " + raw[cut:]  # espace = continuation
    chunks.append(raw)
    return "\r\n".join(c.decode("utf-8") for c in chunks)


def esc(text: str) -> str:
    """Échappe les caractères spéciaux d'une valeur texte ICS."""
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def uid_for(name: str, year: int, domain: str = "anniversaires.local") -> str:
    h = hashlib.md5(f"{name}-{year}".encode("utf-8")).hexdigest()[:12]
    return f"{h}@{domain}"


def age_word(age: int) -> str:
    return f"{age} an" if age == 1 else f"{age} ans"


def parse_birthdate(value: str):
    """Retourne (mois, jour, annee|None). Accepte 'AAAA-MM-JJ' ou '--MM-JJ'."""
    value = value.strip()
    if value.startswith("--"):  # année inconnue (format vCard/RFC 6350)
        month, day = value[2:].split("-")
        return int(month), int(day), None
    d = dt.date.fromisoformat(value)
    return d.month, d.day, d.year


def build_events(person: dict, years: int, today: dt.date,
                 key: bytes | None = None) -> list[str]:
    name = person["name"].strip()
    ref = person.get("ref", name).strip()  # identifiant stable, jamais affiché
    month, day, birth_year = parse_birthdate(person["birthdate"])
    blocks = []

    for n in range(0, years + 1):
        year = today.year + n
        # Gère le 29 février : reporté au 28 si l'année n'est pas bissextile.
        try:
            occ = dt.date(year, month, day)
        except ValueError:
            occ = dt.date(year, 2, 28)

        # On saute les occurrences déjà passées cette année.
        if occ < today:
            continue

        if birth_year is not None:
            age = year - birth_year
            label = f"{name} ({age_word(age)})"
        else:
            label = name

        if key is not None:
            # Titre chiffré : aucun prénom en clair dans le fichier publié.
            summary = "🔒 " + encrypt_label(key, label)
            desc = "Anniversaire (titre chiffré — déchiffrement via la clé)"
        else:
            summary = f"🎂 {label}"
            if birth_year is not None:
                desc = f"Né(e) le {day:02d}/{month:02d}/{birth_year}"
            else:
                desc = f"Anniversaire (le {day:02d}/{month:02d}, année de naissance inconnue)"

        dtstart = occ.strftime("%Y%m%d")
        dtend = (occ + dt.timedelta(days=1)).strftime("%Y%m%d")
        stamp = today.strftime("%Y%m%dT000000Z")

        ev = [
            "BEGIN:VEVENT",
            f"UID:{uid_for(ref, year)}",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{dtstart}",
            f"DTEND;VALUE=DATE:{dtend}",
            "TRANSP:TRANSPARENT",
            f"SUMMARY:{esc(summary)}",
            f"DESCRIPTION:{esc(desc)}",
            "CATEGORIES:ANNIVERSAIRE",
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            "TRIGGER:-P1D",
            f"DESCRIPTION:{esc(summary)}",
            "END:VALARM",
            "END:VEVENT",
        ]
        blocks.append("\r\n".join(fold(l) for l in ev))

    return blocks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="data/contacts.json")
    ap.add_argument("--output", default="public/anniversaires.ics")
    ap.add_argument("--years", type=int, default=80,
                    help="Nombre d'années générées en avance (défaut : 80)")
    ap.add_argument("--require-key", action="store_true",
                    help="Échoue si CALENDAR_KEY est absent (sécurité CI : "
                         "interdit de publier des prénoms en clair).")
    args = ap.parse_args()

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    cal_name = data.get("calendar_name", "Anniversaires")
    tz = data.get("timezone", "Europe/Paris")
    today = dt.date.today()
    key = load_key()
    if args.require_key and key is None:
        raise SystemExit("❌ CALENDAR_KEY absent : génération refusée (--require-key). "
                         "Ajoute le secret avant de publier.")

    head = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//anniversaires-calendar//FR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{esc(cal_name)}",
        f"X-WR-TIMEZONE:{tz}",
        "X-PUBLISHED-TTL:PT12H",
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
    ]

    # Liste d'exclusion : on saute toute personne dont le name OU le ref y figure.
    exclude = {e.strip().lower() for e in data.get("exclude", [])}

    body = []
    kept = 0
    for person in data["people"]:
        ids = {person["name"].strip().lower(),
               person.get("ref", person["name"]).strip().lower()}
        if ids & exclude:
            continue
        body.extend(build_events(person, args.years, today, key))
        kept += 1

    lines = ["\r\n".join(fold(l) for l in head)] + body + ["END:VCALENDAR"]
    ics = "\r\n".join(lines) + "\r\n"

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(ics, encoding="utf-8")
    mode = "🔒 CHIFFRÉ" if key else "⚠️  EN CLAIR (CALENDAR_KEY non défini)"
    print(f"✅ {out} généré — {kept} personnes (sur {len(data['people'])}, "
          f"{len(exclude)} exclusion(s)), fenêtre {args.years} ans — {mode}.")


if __name__ == "__main__":
    main()
