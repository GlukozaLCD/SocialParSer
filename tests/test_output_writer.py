import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from src import output_writer


class TestWriteResult(unittest.TestCase):
    def test_writes_expected_filename_and_valid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_output_dir = Path(tmp) / "output"
            with patch.object(output_writer, "OUTPUT_DIR", fake_output_dir):
                day = date(2026, 8, 27)
                result = {"generated_at": "2026-08-27T09:00:00+00:00", "window_hours": 24, "publics": [], "errors": []}

                path = output_writer.write_result(result, day)

                self.assertEqual(path, fake_output_dir / "links_2026-08-27.json")
                self.assertTrue(path.exists())
                self.assertEqual(json.loads(path.read_text(encoding="utf-8")), result)


if __name__ == "__main__":
    unittest.main()
