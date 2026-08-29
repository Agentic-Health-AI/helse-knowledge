from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import verify_screening as verifier


class ScreeningVerifierTests(unittest.TestCase):
    def test_committed_screening_passes(self):
        self.assertEqual([], verifier.verify())

    def test_human_actor_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            screening = Path(temporary) / "screening"
            shutil.copytree(verifier.SCREENING, screening)
            event_path = screening / "verification-events.jsonl"
            lines = event_path.read_text(encoding="utf-8").splitlines()
            event = json.loads(lines[0])
            event["actor_type"] = "human"
            lines[0] = json.dumps(event, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            event_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            errors = verifier.verify(screening)
            self.assertIn("screening file hash: verification_events", errors)
            self.assertIn("screening actor chain", errors)

    def test_changed_decision_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            screening = Path(temporary) / "screening"
            shutil.copytree(verifier.SCREENING, screening)
            path = screening / "screenings.jsonl"
            lines = path.read_text(encoding="utf-8").splitlines()
            record = json.loads(lines[0])
            record["decision"] = "excluded" if record["decision"] != "excluded" else "included"
            lines[0] = json.dumps(record, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            errors = verifier.verify(screening)
            self.assertIn("screening file hash: screenings", errors)
            self.assertIn("screening discovery state", errors)


if __name__ == "__main__":
    unittest.main()
