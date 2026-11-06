"""deploy_worker --allow-added-worker-routes: only declared broker allow rules may be added."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra"))
from deploy_worker import added_routes_check, normalized, with_added_routes  # noqa: E402
from render_policy import WORKER_ROUTES  # noqa: E402

REFERENCE = json.loads((ROOT / "docs/runtime/evidence/worker-12-effective-policy.json").read_text(encoding="utf-8"))


class AddedRoutesTests(unittest.TestCase):
    def test_adds_only_missing_worker_routes_to_the_guide_endpoint(self):
        expected, added = with_added_routes(REFERENCE["policy"], "hangul-worker-12", WORKER_ROUTES)
        self.assertEqual(added, [("POST", "/worker/progress"), ("POST", "/worker/wiki"),
                                 ("POST", "/worker/review-results"), ("POST", "/worker/probe-results")])
        self.assertFalse(any("canary" in path for _, path in added))
        guide = expected["network_policies"]["_provider_hangul_worker_12_guide"]["endpoints"][0]
        original = REFERENCE["policy"]["network_policies"]["_provider_hangul_worker_12_guide"]["endpoints"][0]
        self.assertEqual({k: v for k, v in guide.items() if k != "rules"}, {k: v for k, v in original.items() if k != "rules"})
        for name in ("local_model", "service_health"):
            self.assertEqual(expected["network_policies"][name], REFERENCE["policy"]["network_policies"][name])
        for key in ("filesystem_policy", "landlock", "process", "version"):
            self.assertEqual(expected[key], REFERENCE["policy"][key])

    def test_reference_itself_is_unchanged_and_result_is_idempotent(self):
        before = json.dumps(REFERENCE["policy"], sort_keys=True)
        expected, _ = with_added_routes(REFERENCE["policy"], "hangul-worker-12", WORKER_ROUTES)
        self.assertEqual(json.dumps(REFERENCE["policy"], sort_keys=True), before)
        again, added = with_added_routes(expected, "hangul-worker-12", WORKER_ROUTES)
        self.assertEqual(added, [])
        self.assertEqual(normalized(again), normalized(expected))

    def test_correct_policy_in_any_rule_order_is_accepted(self):
        expected, _ = with_added_routes(REFERENCE["policy"], "hangul-worker-12", WORKER_ROUTES)
        actual = json.loads(json.dumps(expected))
        for group in actual["network_policies"].values():
            for endpoint in group["endpoints"]:
                endpoint["rules"].reverse()
        self.assertEqual(added_routes_check(actual, REFERENCE["policy"], "hangul-worker-12", WORKER_ROUTES)[-2:],
                         [("POST", "/worker/review-results"), ("POST", "/worker/probe-results")])

    def test_an_extra_undeclared_rule_is_detected(self):
        expected, _ = with_added_routes(REFERENCE["policy"], "hangul-worker-12", WORKER_ROUTES)
        for group, rule in (("_provider_hangul_worker_12_guide", {"allow": {"method": "POST", "path": "/worker/canary"}}),
                            ("local_model", {"allow": {"method": "POST", "path": "/v1/completions"}})):
            tampered = json.loads(json.dumps(expected))
            tampered["network_policies"][group]["endpoints"][0]["rules"].append(rule)
            with self.assertRaises(RuntimeError):
                added_routes_check(tampered, REFERENCE["policy"], "hangul-worker-12", WORKER_ROUTES)
        widened = json.loads(json.dumps(expected))
        widened["filesystem_policy"]["read_write"].append("/app")
        with self.assertRaises(RuntimeError):
            added_routes_check(widened, REFERENCE["policy"], "hangul-worker-12", WORKER_ROUTES)

    def test_canary_in_declared_routes_is_refused(self):
        routes = [*WORKER_ROUTES, ("POST", "/worker/canary")]
        expected, _ = with_added_routes(REFERENCE["policy"], "hangul-worker-12", routes)
        with self.assertRaisesRegex(RuntimeError, "canary"):
            added_routes_check(expected, REFERENCE["policy"], "hangul-worker-12", routes)



class AddableRoutesTests(unittest.TestCase):
    def test_wildcard_or_unlisted_additions_are_refused(self):
        for route in (("POST", "/worker/*"), ("POST", "/worker/**"), ("GET", "/worker/results")):
            routes = [*WORKER_ROUTES, route]
            expected, _ = with_added_routes(REFERENCE["policy"], "hangul-worker-12", routes)
            with self.subTest(route=route), self.assertRaisesRegex(RuntimeError, "declared F2/F3"):
                added_routes_check(expected, REFERENCE["policy"], "hangul-worker-12", routes)


if __name__ == "__main__":
    unittest.main()
