from __future__ import annotations

from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from finalize_screening import FACT_ORDER, reduce_decision
from run_llm_screening import normalize_record_order, output_schema


class ScreeningPipelineTests(unittest.TestCase):
    def facts(self, value=True):
        return {name: {"value": value, "locations": ["title"]} for name in FACT_ORDER}

    def assessments(self, outcome="supported"):
        return {name: {"outcome": outcome, "locations": ["title"]} for name in FACT_ORDER}

    def test_all_supported_true_is_included(self):
        decision, reason, _ = reduce_decision(self.facts(), self.assessments())
        self.assertEqual(("included", None), (decision, reason))

    def test_supported_false_uses_controlled_reason(self):
        facts = self.facts()
        facts["serum_or_plasma_25_oh_d"]["value"] = False
        decision, reason, _ = reduce_decision(facts, self.assessments())
        self.assertEqual(("excluded", "wrong-analyte-or-specimen"), (decision, reason))

    def test_unsupported_fact_is_awaiting_full_text(self):
        assessments = self.assessments()
        assessments["adults_in_scope"]["outcome"] = "unknown"
        decision, reason, audited = reduce_decision(self.facts(), assessments)
        self.assertEqual(("awaiting-full-text", None), (decision, reason))
        self.assertIsNone(audited["adults_in_scope"])

    def test_output_schema_requires_each_record_id_as_property(self):
        records = [
            {"record_id": record_id, "publication_types": {"location_id": "publication_types"}, "title": {"location_id": "title"}, "abstract_sections": []}
            for record_id in ("record-a", "record-b")
        ]
        schema = output_schema(records, "parser")
        record_schema = schema["properties"]["records"]
        self.assertEqual(["record-a", "record-b"], record_schema["required"])
        self.assertFalse(record_schema["additionalProperties"])

    def test_record_map_is_normalized_to_input_order(self):
        payload = {"records": {"record-b": {"facts": {}, "notes": ""}, "record-a": {"facts": {}, "notes": ""}}}
        normalize_record_order(payload, [{"record_id": "record-a"}, {"record_id": "record-b"}], "parser")
        self.assertEqual(["record-a", "record-b"], [record["record_id"] for record in payload["records"]])


if __name__ == "__main__":
    unittest.main()
