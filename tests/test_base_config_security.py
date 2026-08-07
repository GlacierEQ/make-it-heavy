from pathlib import Path
import unittest

import yaml


class BaseConfigurationSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))

    def test_smithery_has_no_base_connection_ids(self):
        self.assertEqual(self.config["smithery"]["allowed_connections"], [])

    def test_smithery_is_not_globally_allowlisted_in_base_config(self):
        self.assertNotIn("smithery_mcp", self.config["tools"]["allowlist"])

    def test_no_base_worker_profile_allowlists_smithery(self):
        for profile in self.config["apex_agents"]:
            with self.subTest(role=profile["role"]):
                self.assertNotIn("smithery_mcp", profile["allowed_tools"])

    def test_local_write_and_memory_capabilities_remain_enabled(self):
        self.assertIn("write_file", self.config["tools"]["allowlist"])
        self.assertIn("memory", self.config["tools"]["allowlist"])
        self.assertIs(self.config["tools"]["mutation_enabled"], True)


if __name__ == "__main__":
    unittest.main()
