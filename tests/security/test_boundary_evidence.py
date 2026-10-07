"""Fail-closed checks for joining recorded runtime evidence."""
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

MODULE_PATH = Path(__file__).with_name("verify_boundary_evidence.py")
spec = importlib.util.spec_from_file_location("boundary_verifier", MODULE_PATH)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)
EVIDENCE = Path(__file__).resolve().parents[2] / "docs/runtime/evidence"


class BoundaryEvidenceTests(unittest.TestCase):
    def test_verdict_only_row_is_ignored(self):
        original = Path.read_text

        def read(path, *args, **kwargs):
            text = original(path, *args, **kwargs)
            if path.name == "boundary-matrix-01.log":
                text += '\n{"verdict":"INCOMPLETE","required":"external evidence"}\n'
            return text

        with patch.object(Path, "read_text", read):
            self.assertTrue(all(verifier.verify(EVIDENCE).values()))

    def test_receiver_delivery_prevents_pass(self):
        original = Path.read_text

        def read(path, *args, **kwargs):
            if path.name == "receiver-8013-counts.json":
                return json.dumps({"GET_health": 1, "POST_health": 0, "POST_reservations": 0})
            return original(path, *args, **kwargs)

        with patch.object(Path, "read_text", read):
            checks = verifier.verify(EVIDENCE)
        self.assertFalse(checks["forbidden_receiver_count"])
        self.assertFalse(all(checks.values()))


if __name__ == "__main__":
    unittest.main()
