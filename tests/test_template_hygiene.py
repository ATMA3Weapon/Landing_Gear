from __future__ import annotations

import json
import unittest
from pathlib import Path

from landing_gear.install_support import load_service_metadata


class TemplateHygieneTests(unittest.TestCase):
    def test_runtime_metadata_does_not_contain_stale_service_names(self):
        repo_root = Path(__file__).resolve().parents[1]
        payload = load_service_metadata(repo_root / 'conf.example.toml')
        text = json.dumps(payload, sort_keys=True)

        self.assertNotIn('broker_runtime', text)
        self.assertNotIn('/api/diagnostics', text)
        self.assertNotIn('broker_domain', text)
        self.assertNotIn('audit_max_events', text)
        self.assertNotIn('terminal_job_max_age_seconds', text)

    def test_live_conf_toml_is_not_committed(self):
        repo_root = Path(__file__).resolve().parents[1]
        self.assertFalse((repo_root / 'conf.toml').exists())
        self.assertIn('conf.toml', (repo_root / '.gitignore').read_text())


if __name__ == '__main__':
    unittest.main()
