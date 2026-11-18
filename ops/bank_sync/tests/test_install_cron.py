import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from install_cron import confirmation_message


class CronInstallerTests(unittest.TestCase):
    def test_confirmation_reports_the_configured_schedule_and_unit(self):
        self.assertEqual(
            confirmation_message('0 2 * * 1', 'bank-sync.service'),
            'Installed one cron entry: 0 2 * * 1 UTC, scoped to bank-sync.service.',
        )


if __name__ == '__main__':
    unittest.main()
