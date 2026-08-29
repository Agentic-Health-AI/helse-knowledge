from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import verify_repository as verifier


class RepositoryVerifierTests(unittest.TestCase):
    def bundle(self):
        return copy.deepcopy(verifier.load_bundle())

    def rejects(self, mutate, expected):
        bundle = self.bundle()
        mutate(bundle)
        self.assertIn(expected, verifier.validate_bundle(bundle))

    def test_valid_fixture_passes(self):
        self.assertEqual([], verifier.validate())

    def test_schema_required_field_is_enforced(self):
        self.rejects(
            lambda b: b["collections"]["claims"][0].pop("claim_type"),
            "schema violation: claims[0] missing claim_type",
        )

    def test_schema_enum_is_enforced(self):
        self.rejects(
            lambda b: b["collections"]["discoveries"][0].update(state="invented"),
            "schema violation: discoveries[0] state enum",
        )

    def test_duplicate_ids_are_rejected(self):
        self.rejects(
            lambda b: b["collections"]["claims"][0].update(id=b["collections"]["syntheses"][0]["id"]),
            "duplicate canonical id",
        )

    def test_missing_search_source_trace_is_rejected(self):
        self.rejects(
            lambda b: b["collections"]["discoveries"][0].pop("source_url"),
            "missing search/source trace",
        )

    def test_search_protocol_mismatch_is_rejected(self):
        self.rejects(
            lambda b: b["collections"]["searches"][0].update(protocol_id="https://example.invalid/wrong"),
            "search protocol mismatch",
        )

    def test_record_query_trace_mismatch_is_rejected(self):
        self.rejects(
            lambda b: b["collections"]["discoveries"][0].update(query_ids=["q2-distribution"]),
            "record query trace mismatch",
        )

    def test_included_without_screening_is_rejected(self):
        self.rejects(
            lambda b: b["collections"]["screenings"].pop(0),
            "screened state without screening decision",
        )

    def test_exclusion_without_controlled_reason_is_rejected(self):
        self.rejects(
            lambda b: b["collections"]["screenings"][2].update(exclusion_reason=None),
            "exclusion without controlled reason",
        )

    def test_invalid_state_transition_is_rejected(self):
        self.rejects(
            lambda b: b["collections"]["screenings"][0].update(state_history=["discovered", "included"]),
            "invalid state transition",
        )

    def test_broken_screening_event_is_rejected(self):
        self.rejects(
            lambda b: b["collections"]["screenings"][0].update(reviewer_events=["https://example.invalid/missing"]),
            "broken screening event reference",
        )

    def test_unknown_relation_type_is_rejected_by_schema(self):
        self.rejects(
            lambda b: b["collections"]["relations"][0].update(relation_type="invented"),
            "schema violation: relations[0] relation_type enum",
        )

    def test_candidate_auto_merge_is_rejected(self):
        def mutate(bundle):
            bundle["collections"]["relations"][1].update(
                relation_type="duplicate-candidate", auto_merged=True
            )

        self.rejects(mutate, "candidate auto-merge")

    def test_self_referential_relation_is_rejected(self):
        self.rejects(
            lambda b: b["collections"]["relations"][2].update(
                from_id=b["collections"]["relations"][2]["to_id"]
            ),
            "broken relation reference",
        )

    def test_extraction_from_excluded_record_is_rejected(self):
        self.rejects(
            lambda b: b["collections"]["extractions"][0].update(
                record_id=b["collections"]["discoveries"][2]["id"]
            ),
            "extraction from non-included record",
        )

    def test_unknown_extraction_question_is_rejected(self):
        self.rejects(
            lambda b: b["collections"]["extractions"][0].update(question_id="q99"),
            "unknown extraction question",
        )

    def test_broken_claim_reference_is_rejected(self):
        self.rejects(
            lambda b: b["collections"]["claims"][0].update(synthesis_id="https://example.invalid/missing"),
            "broken claim references",
        )

    def test_claim_evidence_must_belong_to_synthesis(self):
        def mutate(bundle):
            clone = copy.deepcopy(bundle["collections"]["extractions"][0])
            clone["id"] = "https://example.invalid/helse-knowledge/synthetic/extraction/second"
            bundle["collections"]["extractions"].append(clone)
            bundle["collections"]["claims"][0]["evidence_ids"] = [clone["id"]]

        self.rejects(mutate, "claim evidence not in synthesis")

    def test_numeric_claim_requires_full_context(self):
        self.rejects(
            lambda b: b["collections"]["claims"][0].update(numeric_value=1),
            "numeric claim without required context",
        )

    def test_stable_conclusion_requires_evidence(self):
        self.rejects(
            lambda b: b["collections"]["syntheses"][0].update(
                conclusion_status="stable", evidence_ids=[]
            ),
            "conclusion lacks evidence",
        )

    def test_stable_preprint_only_conclusion_is_rejected(self):
        def mutate(bundle):
            bundle["collections"]["syntheses"][0]["conclusion_status"] = "stable"
            bundle["collections"]["discoveries"][0]["peer_review_status"] = "preprint"

        self.rejects(mutate, "stable conclusion from preprints only")

    def test_preprint_final_double_counting_is_rejected(self):
        def mutate(bundle):
            clone = copy.deepcopy(bundle["collections"]["extractions"][0])
            clone["id"] = "https://example.invalid/helse-knowledge/synthetic/extraction/second"
            clone["verification_events"] = []
            bundle["collections"]["extractions"].append(clone)
            bundle["collections"]["syntheses"][0]["evidence_ids"].append(clone["id"])

        self.rejects(mutate, "preprint/final double-counting")

    def test_active_claim_cannot_use_retracted_source(self):
        def mutate(bundle):
            clone = copy.deepcopy(bundle["collections"]["extractions"][0])
            clone["id"] = "https://example.invalid/helse-knowledge/synthetic/extraction/retracted"
            clone["record_id"] = bundle["collections"]["discoveries"][4]["id"]
            clone["verification_events"] = []
            bundle["collections"]["extractions"].append(clone)
            synthesis = bundle["collections"]["syntheses"][0]
            synthesis.update(conclusion_status="stable", evidence_ids=[clone["id"]])
            bundle["collections"]["claims"][0].update(
                status="active", evidence_ids=[clone["id"]]
            )

        self.rejects(mutate, "active claim supported by retraction")

    def test_medrxiv_cannot_be_labelled_peer_reviewed(self):
        self.rejects(
            lambda b: b["collections"]["discoveries"][1].update(
                peer_review_status="peer-reviewed"
            ),
            "preprint labelled peer-reviewed",
        )

    def test_machine_cannot_claim_human_verification(self):
        self.rejects(
            lambda b: b["collections"]["verification_events"][0].update(
                action="human-verified"
            ),
            "machine-authored human verification",
        )

    def test_unsubstantiated_human_event_is_rejected(self):
        self.rejects(
            lambda b: b["collections"]["verification_events"][0].update(
                actor_type="human", action="verified"
            ),
            "unsubstantiated human verification event",
        )

    def test_nested_private_value_is_scanned(self):
        self.rejects(
            lambda b: b["collections"]["extractions"][0]["source_statements"].append(
                "private.person@example.com"
            ),
            "forbidden personal/private value or credential",
        )

    def test_private_field_variants_are_scanned(self):
        self.rejects(
            lambda b: b["collections"]["discoveries"][0].update(
                medical_record_number="synthetic"
            ),
            "forbidden personal/private structured field",
        )

    def test_generated_dependency_is_rejected(self):
        self.rejects(
            lambda b: b["collections"]["claims"][0].update(
                statement="depends on generated/index.db"
            ),
            "canonical dependence on generated artifacts",
        )

    def test_pin_mismatch_is_rejected(self):
        self.rejects(
            lambda b: b["pin"]["pin"].update(sha256="0" * 64),
            "OKF pin mismatch: sha256",
        )


if __name__ == "__main__":
    unittest.main()
