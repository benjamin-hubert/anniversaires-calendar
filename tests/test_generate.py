"""Tests de la lecture de source de generate.py (clair ou .enc)."""

import base64
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import crypto_contacts as cc  # noqa: E402
import generate  # noqa: E402

KEY = bytes(range(32))
SAMPLE = {"calendar_name": "Test", "people": [{"name": "Léa", "birthdate": "--06-08"}]}


class TestLoadContacts(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.plain = self.tmp / "contacts.json"
        self.enc = self.tmp / "contacts.json.enc"

    def _write_enc(self):
        self.enc.write_text(cc.encrypt_blob(KEY, json.dumps(SAMPLE)), encoding="utf-8")

    def test_reads_plaintext_when_present(self):
        self.plain.write_text(json.dumps(SAMPLE), encoding="utf-8")
        self.assertEqual(generate.load_contacts(self.plain), SAMPLE)

    def test_decrypts_enc_when_plaintext_absent(self):
        self._write_enc()
        self.assertEqual(generate.load_contacts(self.plain, key=KEY), SAMPLE)

    def test_plaintext_preferred_over_enc(self):
        self.plain.write_text(json.dumps(SAMPLE), encoding="utf-8")
        self.enc.write_text("blob-corrompu", encoding="utf-8")
        # Le clair fait foi : pas de tentative de déchiffrement du .enc.
        self.assertEqual(generate.load_contacts(self.plain, key=KEY), SAMPLE)

    def test_error_when_nothing_available(self):
        with self.assertRaises(SystemExit):
            generate.load_contacts(self.plain, key=KEY)


class TestGenerateEquivalence(unittest.TestCase):
    """Le .ics produit depuis le .enc doit être identique à celui du clair."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.plain = self.tmp / "contacts.json"
        self.enc = self.tmp / "contacts.json.enc"
        self.plain.write_text(json.dumps(SAMPLE), encoding="utf-8")
        self.enc.write_text(cc.encrypt_blob(KEY, json.dumps(SAMPLE)), encoding="utf-8")

    def _run(self, input_path):
        out = self.tmp / f"out-{input_path.name}.ics"
        env = dict(os.environ, CALENDAR_KEY=base64.urlsafe_b64encode(KEY).decode())
        root = Path(__file__).resolve().parent.parent
        subprocess.run(
            [sys.executable, str(root / "generate.py"),
             "--input", str(input_path), "--output", str(out), "--years", "1"],
            check=True, cwd=root, env=env, capture_output=True,
        )
        return out.read_text(encoding="utf-8")

    def test_enc_and_plaintext_produce_identical_ics(self):
        from_plain = self._run(self.plain)
        self.plain.unlink()  # ne laisser que le .enc
        from_enc = self._run(self.plain)
        self.assertEqual(from_plain, from_enc)


if __name__ == "__main__":
    unittest.main()
