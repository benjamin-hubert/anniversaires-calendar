"""Tests du scellage automatique de manage.py."""

import base64
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import crypto_contacts as cc  # noqa: E402
import manage  # noqa: E402

KEY = bytes(range(32))
KEY_B64 = base64.urlsafe_b64encode(KEY).decode()
SAMPLE = {"calendar_name": "Test", "exclude": [], "people": [{"name": "Léa", "birthdate": "--06-08"}]}


class TestSeal(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.plain = self.tmp / "contacts.json"
        self.enc = self.tmp / "contacts.json.enc"
        self._saved = os.environ.get("CALENDAR_KEY")

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("CALENDAR_KEY", None)
        else:
            os.environ["CALENDAR_KEY"] = self._saved

    def test_save_writes_plaintext_and_enc_with_key(self):
        os.environ["CALENDAR_KEY"] = KEY_B64
        manage.save(SAMPLE, self.plain)
        self.assertEqual(json.loads(self.plain.read_text(encoding="utf-8")), SAMPLE)
        self.assertTrue(self.enc.exists())
        self.assertEqual(
            json.loads(cc.decrypt_blob(KEY, self.enc.read_text(encoding="utf-8"))),
            SAMPLE,
        )

    def test_save_without_key_skips_enc(self):
        os.environ.pop("CALENDAR_KEY", None)
        manage.save(SAMPLE, self.plain)
        self.assertTrue(self.plain.exists())
        self.assertFalse(self.enc.exists())

    def test_load_reads_plaintext(self):
        self.plain.write_text(json.dumps(SAMPLE), encoding="utf-8")
        self.assertEqual(manage.load(self.plain), SAMPLE)

    def test_load_decrypts_enc_when_plaintext_absent(self):
        os.environ["CALENDAR_KEY"] = KEY_B64
        self.enc.write_text(cc.encrypt_blob(KEY, json.dumps(SAMPLE)), encoding="utf-8")
        self.assertEqual(manage.load(self.plain), SAMPLE)


if __name__ == "__main__":
    unittest.main()
