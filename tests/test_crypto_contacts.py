"""Tests du module de chiffrement partagé crypto_contacts."""

import base64
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import crypto_contacts as cc  # noqa: E402

KEY = bytes(range(32))  # clé 32 octets déterministe pour les tests
KEY_B64 = base64.urlsafe_b64encode(KEY).decode()


class TestBlobCrypto(unittest.TestCase):
    def test_round_trip(self):
        token = cc.encrypt_blob(KEY, "Bonjour é à ç")
        self.assertEqual(cc.decrypt_blob(KEY, token), "Bonjour é à ç")

    def test_deterministic(self):
        # Même contenu -> même jeton (diffs git propres).
        self.assertEqual(
            cc.encrypt_blob(KEY, "même texte"),
            cc.encrypt_blob(KEY, "même texte"),
        )

    def test_wrong_key_rejected(self):
        token = cc.encrypt_blob(KEY, "secret")
        wrong = bytes(range(1, 33))
        with self.assertRaises(Exception):
            cc.decrypt_blob(wrong, token)


class TestLoadKey(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.get("CALENDAR_KEY")

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("CALENDAR_KEY", None)
        else:
            os.environ["CALENDAR_KEY"] = self._saved

    def test_absent_returns_none(self):
        os.environ.pop("CALENDAR_KEY", None)
        self.assertIsNone(cc.load_key())

    def test_valid_returns_32_bytes(self):
        os.environ["CALENDAR_KEY"] = KEY_B64
        self.assertEqual(cc.load_key(), KEY)

    def test_wrong_length_raises(self):
        os.environ["CALENDAR_KEY"] = base64.urlsafe_b64encode(b"short").decode()
        with self.assertRaises(SystemExit):
            cc.load_key()


if __name__ == "__main__":
    unittest.main()
