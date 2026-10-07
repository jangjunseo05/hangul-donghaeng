"""Offline evaluation-boundary checks; no actual forbidden directories or GPU."""
import importlib.util
import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("launch_challenge", ROOT / "infra/launch_challenge.py")
launch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launch)


class ChallengePolicyTests(unittest.TestCase):
    def test_only_input_readonly_output_writable(self):
        policy = json.loads((ROOT / "policy/challenge-policy.json").read_text())
        self.assertTrue(launch.policy_compatible(policy))
        policy["filesystem_policy"]["read_write"].append("/hackathon")
        self.assertFalse(launch.policy_compatible(policy))

    def test_no_broker_or_audit_expansion(self):
        policy = json.loads((ROOT / "policy/challenge-policy.json").read_text())
        policy["network_policies"]["local_model"]["endpoints"][0]["enforcement"] = "audit"
        self.assertFalse(launch.policy_compatible(policy))

    def test_gateway_materialized_policy_name(self):
        policy = json.loads((ROOT / "policy/challenge-policy.json").read_text())
        policy["network_policies"]["local_model"]["name"] = "local_model"
        policy["filesystem_policy"]["read_only"].append("/var/log")
        self.assertTrue(launch.policy_compatible(policy))

    def test_reject_forbidden_path_before_access(self):
        with self.assertRaisesRegex(ValueError, "forbidden_input_path"):
            launch.safe_source(Path("/hackathon/restricted/never-opened"))

    def test_public_input_bytes_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / "source", Path(tmp) / "stage"
            source.mkdir()
            content = "문화 자료\n".encode("utf-8")
            (source / "public.md").write_bytes(content)
            manifest = launch.stage_inputs(source, target)
            self.assertEqual((target / "public.md").read_bytes(), content)
            self.assertEqual(manifest[0]["bytes"], len(content))

    def test_reparse_rejected_without_reading(self):
        info = SimpleNamespace(st_mode=0o40755, st_file_attributes=0x400)
        with patch.object(Path, "lstat", return_value=info), patch.object(Path, "read_bytes") as read:
            with self.assertRaisesRegex(ValueError, "symlink_input_path"):
                launch.safe_source(Path("safe-public-input"))
            read.assert_not_called()

    def test_output_export_rejects_path_escape(self):
        response = SimpleNamespace(stdout=json.dumps([{"path": "../answer.json", "content": "e30="}]))
        with tempfile.TemporaryDirectory() as tmp, patch.object(launch, "command", return_value=response):
            with self.assertRaisesRegex(ValueError, "unsafe_output_name"):
                launch.export_outputs("hangul-eval-01", Path(tmp))
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_output_export_preserves_bytes(self):
        name = "challenge-20261007T081308Z-4098dda9fa2b/answer.json"
        response = SimpleNamespace(stdout=json.dumps([{"path": name, "content": base64.b64encode(b'{}\n').decode()}]))
        with tempfile.TemporaryDirectory() as tmp, patch.object(launch, "command", return_value=response):
            manifest = launch.export_outputs("hangul-eval-01", Path(tmp))
            self.assertEqual((Path(tmp) / name).read_bytes(), b'{}\n')
            self.assertEqual(manifest[0]["bytes"], 3)


if __name__ == "__main__":
    unittest.main()
