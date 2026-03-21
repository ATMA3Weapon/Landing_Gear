from __future__ import annotations

import json
import unittest
from pathlib import Path

from landing_gear.install_support import load_service_metadata


class TemplateHygieneTests(unittest.TestCase):
    def test_runtime_metadata_does_not_contain_stale_service_names(self):
        payload = load_service_metadata(Path(__file__).resolve().parents[1] / 'conf.toml')
        text = json.dumps(payload, sort_keys=True)

        self.assertNotIn('broker_runtime', text)
        self.assertNotIn('/api/diagnostics', text)
        self.assertNotIn('broker_domain', text)
        self.assertNotIn('audit_max_events', text)
        self.assertNotIn('terminal_job_max_age_seconds', text)


if __name__ == '__main__':
    unittest.main()
