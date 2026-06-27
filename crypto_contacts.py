#!/usr/bin/env python3
"""Primitive de chiffrement partagée entre generate.py et manage.py.

Chiffre/déchiffre un texte en AES-256-GCM avec un nonce dérivé du contenu clair
(HMAC-SHA256) : le chiffrement est déterministe (même entrée → même jeton), ce
qui donne des diffs git propres et évite les réécritures inutiles. Chaque message
distinct obtient un nonce distinct ; il n'y a donc jamais de réutilisation de
nonce entre messages différents.
"""

import base64
import hashlib
import hmac
import os
from pathlib import Path

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:  # chiffrement indisponible sans le module cryptography
    AESGCM = None


def _load_dotenv() -> None:
    """Charge un .env local (clé=valeur) sans écraser l'environnement existant.

    Sans dépendance externe : utilisé en local pour fournir CALENDAR_KEY. En CI,
    le secret est déjà dans l'environnement et le .env est absent, donc no-op.
    """
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(name, value)


def load_key() -> bytes | None:
    """Charge la clé depuis CALENDAR_KEY (base64 de 32 octets), ou None."""
    _load_dotenv()
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


def encrypt_blob(key: bytes, plaintext: str) -> str:
    """Chiffrement AES-256-GCM déterministe → jeton base64 urlsafe."""
    data = plaintext.encode("utf-8")
    nonce = hmac.new(key, data, hashlib.sha256).digest()[:12]
    ct = AESGCM(key).encrypt(nonce, data, None)
    return base64.urlsafe_b64encode(nonce + ct).decode("ascii")


def decrypt_blob(key: bytes, token: str) -> str:
    """Inverse exact de encrypt_blob()."""
    raw = base64.urlsafe_b64decode(token.encode("ascii"))
    nonce, ct = raw[:12], raw[12:]
    return AESGCM(key).decrypt(nonce, ct, None).decode("utf-8")
