"""The capability registry must stay honest about platforms that are not built."""
from __future__ import annotations

import unittest

from windows_repair.capabilities import SHARED_PROTOCOL, registry
from windows_repair.catalogue import PROCEDURES
from windows_repair.providers import LIVE_PROCEDURES

_ALLOWED = {
    "PASS", "PARTIAL", "FAIL", "NOT IMPLEMENTED", "BLOCKED", "NOT VERIFIED", "NOT TESTED",
}


class CapabilityRegistryTests(unittest.TestCase):
    def test_registry_covers_procedures_and_does_not_invent_agents(self) -> None:
        rows = registry()
        operations = {item.operation for item in rows if item.platform == "windows"}
        self.assertEqual(operations, set(PROCEDURES))
        live = {item.operation for item in rows if item.platform == "windows" and item.timeout_seconds == 20}
        self.assertEqual(live, set(LIVE_PROCEDURES))
        for item in rows:
            self.assertIn(item.status, _ALLOWED)
            self.assertTrue(item.operation)
            self.assertTrue(item.platform)
            self.assertTrue(item.test_coverage)
            self.assertNotEqual(item.status, "PASS")
        platforms = {item.platform: item.status for item in rows if item.operation == "device-agent"}
        self.assertEqual(platforms["darwin"], "NOT IMPLEMENTED")
        self.assertEqual(platforms["android"], "BLOCKED")
        self.assertEqual(platforms["ios"], "BLOCKED")
        web = next(item for item in rows if item.platform == "web")
        self.assertEqual(web.status, "PARTIAL")
        self.assertIn("loopback", web.notes)
        spooler = next(item for item in rows if item.operation == "print.spooler.restart")
        self.assertEqual(spooler.status, "BLOCKED")
        self.assertIn("macOS", SHARED_PROTOCOL)
        self.assertNotIn("universal", SHARED_PROTOCOL.casefold())
        from agents.mac_catalogue import LIVE_MAC, MAC_CHECKS
        from windows_repair.providers import LIVE_PROCEDURES as live_ids
        from windows_repair.runner import SCRIPTS

        mac = [item for item in rows if item.platform == "darwin" and item.operation != "device-agent"]
        self.assertEqual({item.operation for item in mac}, {check.check_id for check in MAC_CHECKS})
        self.assertEqual(LIVE_MAC, "NOT TESTED")
        for item in mac:
            self.assertEqual(item.status, "NOT TESTED")
            self.assertIn("NOT TESTED", item.notes)
            self.assertIn("No remote Mac agent", item.notes)
            self.assertIsNone(item.timeout_seconds)
        self.assertNotIn("net.firewall.disable", live_ids)
        self.assertNotIn("hw.driver.install", live_ids)
        script_text = "\n".join(SCRIPTS.values()).casefold()
        self.assertNotIn("set-netfirewallprofile", script_text)
        self.assertNotIn("pnputil", script_text)
        self.assertNotIn("sekurlsa", script_text)


if __name__ == "__main__":
    unittest.main()
