from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from landing_gear.config import load_service_config


class ConfigValidationTests(unittest.TestCase):
    def _write(self, text: str) -> Path:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        path = Path(tmpdir.name) / 'conf.toml'
        path.write_text(text)
        return path

    def test_missing_service_name_fails_fast(self):
        path = self._write(
            '''
[service]
version = "0.1.0"
host = "127.0.0.1"
port = 8780
'''
        )
        with self.assertRaisesRegex(ValueError, 'service.name'):
            load_service_config(path)

    def test_invalid_port_is_rejected(self):
        path = self._write(
            '''
[service]
name = "demo"
version = "0.1.0"
host = "127.0.0.1"
port = 70000
'''
        )
        with self.assertRaisesRegex(ValueError, 'service.port'):
            load_service_config(path)

    def test_invalid_log_level_is_rejected(self):
        path = self._write(
            '''
[service]
name = "demo"
version = "0.1.0"
host = "127.0.0.1"
port = 8780

[logging]
level = "TRACE"
'''
        )
        with self.assertRaisesRegex(ValueError, 'logging.level'):
            load_service_config(path)


if __name__ == '__main__':
    unittest.main()
