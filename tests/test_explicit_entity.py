"""Entity selection must fail closed before credentials, cache or HTTP I/O."""
import json
import os
import unittest
from unittest.mock import Mock, patch

from ies_client import qbo_client, qbo_client_rest

MODULES = (qbo_client, qbo_client_rest)
COMPANIES = ("envision", "enspire", "loxsle", "oversight", "pv")


class ExplicitEntityTests(unittest.TestCase):
    def test_missing_entity_on_every_entry_point_even_with_env(self):
        for module in MODULES:
            for environment in ({}, {"QBO_COMPANY": "envision"}):
                with patch.dict(os.environ, environment, clear=True):
                    for function, args in (
                        (module.get_access, ()),
                        (module.query, ("select * from Invoice",)),
                        (module.post, ("invoice", {})),
                    ):
                        for kwargs in ({}, {"company": None}, {"company": ""}, {"company": " "}):
                            with self.subTest(module=module.__name__, function=function.__name__, kwargs=kwargs, environment=environment):
                                with patch.object(module.urllib.request, "urlopen") as http, patch.object(qbo_client, "_rd") as secret, patch.object(qbo_client_rest, "_gce_token") as metadata:
                                    with self.assertRaisesRegex(ValueError, "company is required"):
                                        function(*args, **kwargs)
                                    http.assert_not_called()
                                    secret.assert_not_called()
                                    metadata.assert_not_called()

    def test_every_entity_and_case_is_accepted(self):
        for module in MODULES:
            self.assertEqual(set(module.COMPANIES), set(COMPANIES))
            for name in COMPANIES:
                for value in (name, name.upper()):
                    with self.subTest(module=module.__name__, company=value):
                        self.assertEqual(module._company(value), (name, module.COMPANIES[name]))

    def test_invalid_entity_rejected(self):
        for module in MODULES:
            with self.assertRaisesRegex(ValueError, "unknown QBO company"):
                module.get_access("not-a-company")

    def test_from_env_requires_value(self):
        for module in MODULES:
            for environment in ({}, {"QBO_COMPANY": ""}, {"QBO_COMPANY": " "}):
                with patch.dict(os.environ, environment, clear=True):
                    with self.assertRaises(ValueError):
                        module.from_env()

    def test_from_env_validates_reads_at_call_time_and_logs_only_name(self):
        for module in MODULES:
            for name in COMPANIES:
                with patch.dict(os.environ, {"QBO_COMPANY": name.upper()}):
                    with self.assertLogs(module.__name__, level="INFO") as logs:
                        self.assertEqual(module.from_env(), name)
                    self.assertEqual([r.getMessage() for r in logs.records],
                                     [f"QBO company selected from environment: {name}"])
            with patch.dict(os.environ, {"QBO_COMPANY": "invalid"}):
                with self.assertRaisesRegex(ValueError, "unknown QBO company"):
                    module.from_env()

    def test_requests_forward_explicit_company_and_use_its_realm(self):
        for module in MODULES:
            for name in COMPANIES:
                with patch.dict(os.environ, {"QBO_COMPANY": "invalid"}):
                    with patch.object(module, "get_access", return_value=("fake-access", f"realm-{name}")) as access:
                        response = Mock()
                        response.read.return_value = json.dumps({"QueryResponse": {"ok": True}, "ok": True}).encode()
                        with patch.object(module.urllib.request, "urlopen", return_value=response) as http:
                            self.assertEqual(module.query("select * from Invoice", company=name), {"ok": True})
                            access.assert_called_with(name)
                            self.assertIn(f"/company/realm-{name}/query?", http.call_args.args[0].full_url)
                            self.assertTrue(module.post("invoice", {}, company=name)["ok"])
                            access.assert_called_with(name)
                            self.assertIn(f"/company/realm-{name}/invoice?", http.call_args.args[0].full_url)

    def test_get_access_uses_selected_credentials(self):
        for name in COMPANIES:
            cfg = qbo_client.COMPANIES[name]
            with patch.object(qbo_client, "_rd", side_effect=lambda secret, *args: secret), patch.object(qbo_client.os.path, "exists", return_value=False), patch.object(qbo_client, "_versions", return_value=["1"]), patch.object(qbo_client, "_grant", return_value={"access_token": "fake-access"}), patch.object(qbo_client.os, "makedirs"), patch("builtins.open", unittest.mock.mock_open()):
                self.assertEqual(qbo_client.get_access(name), ("fake-access", cfg["realm"]))
            cfg = qbo_client_rest.COMPANIES[name]
            with patch.object(qbo_client_rest, "_gce_token", return_value="fake-metadata"), patch.object(qbo_client_rest, "_sm_get", side_effect=lambda token, secret, *args: secret), patch.object(qbo_client_rest, "_sm_versions", return_value=["1"]), patch.object(qbo_client_rest, "_grant", return_value={"access_token": "fake-access"}):
                self.assertEqual(qbo_client_rest.get_access(name), ("fake-access", cfg["realm"]))


if __name__ == "__main__":
    unittest.main()
