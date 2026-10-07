import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("render_policy", ROOT / "infra/render_policy.py")
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)

class PolicyTests(unittest.TestCase):
    def test_rejects_unsafe_origins(self):
        for url in ("http://example.com", "https://user:secret@example.com",
                    "https://*.example.com", "https://localhost", "https://169.254.169.254",
                    "https://example.com?key=x", "https://example.com/worker"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                policy.endpoint(url)

    def test_local_host_is_explicit(self):
        self.assertEqual(policy.endpoint("http://host.openshell.internal:8000")["port"], 8000)

    def test_wrong_model_credential_host_rejected(self):
        with self.assertRaises(ValueError):
            policy.generate("https://guide.example.com", "https://other.example.com/v1", True)

    def test_readonly_inputs_and_enforced_network(self):
        docs = policy.generate("https://guide.example.com", "http://host.openshell.internal:8001/v1")
        base = docs["worker-policy.json"]
        self.assertFalse(base["filesystem_policy"]["include_workdir"])
        self.assertEqual(base["filesystem_policy"]["read_write"], ["/tmp", "/dev/null"])
        self.assertEqual(base["landlock"]["compatibility"], "hard_requirement")
        self.assertEqual(base["process"]["run_as_user"], "1000")
        for item in base["network_policies"].values():
            for ep in item["endpoints"]:
                self.assertEqual(ep["enforcement"], "enforce")
        worker_rules = docs["guide-profile.json"]["endpoints"][0]["rules"]
        self.assertEqual({r["allow"]["method"] for r in worker_rules}, {"GET", "POST"})
        self.assertNotIn("/api/**", str(worker_rules))

if __name__ == "__main__":
    unittest.main()
