"""Check metric denominators and prevent mislabeled filtered holdout queries."""
import copy
import json
import unittest

from scripts.evaluate_holdout import PROJECT, content_hash, labeled_queries, summarize


class HoldoutTests(unittest.TestCase):
    def test_multirelevant_recall_is_not_any_hit(self):
        metrics = summarize([
            {"top1": True, "hit": True, "recall": .5, "rr": 1, "seconds": [.01, .02]},
            {"top1": False, "hit": True, "recall": 1, "rr": .5, "seconds": [.03, .04]},
        ])
        self.assertEqual(metrics["hit_rate_at_5"], 1)
        self.assertEqual(metrics["recall_at_5"], .75)
        self.assertEqual(metrics["mrr_at_5"], .75)
        self.assertEqual(metrics["top1"], .5)
        self.assertEqual(metrics["timed_calls"], 4)

    def test_filtered_target_must_be_eligible(self):
        data = json.loads((PROJECT / "fixtures/holdout-v1.json").read_text())
        broken = copy.deepcopy(data)
        broken["extra_queries"][-1]["folder"] = "home"
        with self.assertRaisesRegex(ValueError, "target-excluded-by-filter"):
            labeled_queries(broken)

    def test_frozen_inputs_and_disjoint_query_labels(self):
        # Dataset integrity remains testable when later product code legitimately evolves.
        freeze = json.loads((PROJECT / "fixtures/holdout-v1.freeze.json").read_text())
        self.assertEqual(content_hash(PROJECT / "fixtures/holdout-v1.json"), freeze["files"]["fixtures/holdout-v1.json"])
        data = json.loads((PROJECT / "fixtures/holdout-v1.json").read_text())
        queries = labeled_queries(data)
        self.assertEqual(len(queries), 50)
        self.assertEqual(sum(len(query["targets"]) > 1 for query in queries), 5)


if __name__ == "__main__":
    unittest.main()
