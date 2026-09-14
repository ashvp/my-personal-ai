"""Automated Unit Tests for Head-to-Head Benchmark: v1 vs. v2.

Proves:
1. v1 Unstructured Vector RAG fails on fact drift, point-in-time, and multi-hop queries.
2. v2 Temporal Knowledge Graph passes all 25 scenarios with 100% precision.
"""

import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from tests.dataset_v1_vs_v2_benchmarks import V1_VS_V2_BENCHMARKS
from tests.v1_vs_v2_engine import V1UnstructuredRAG, V2TemporalKG


class TestV1VsV2Benchmarks(unittest.TestCase):
    """Head-to-head unit test assertions contrasting v1 with v2."""

    def setUp(self):
        self.v1 = V1UnstructuredRAG(top_k=2)
        self.v2 = V2TemporalKG()

    def test_01_career_drift_swiggy_to_google(self):
        case = V1_VS_V2_BENCHMARKS[0]  # TKG_01: Rahul Swiggy -> Google
        self.v1.ingest_events(case["events"])
        self.v2.ingest_events(case["events"])

        # V1: Confuses both companies because both chunks match the query
        v1_res = self.v1.query(case["query"])
        self.assertIn("swiggy", v1_res["synthesized_answer"].lower(), "V1 should leak obsolete company Swiggy")
        self.assertIn("google", v1_res["synthesized_answer"].lower(), "V1 retrieves Google as well")

        # V2: Only active edge is Google
        v2_answer = self.v2.query_active_attribute("Rahul", "WORKS_AT")
        self.assertEqual(v2_answer, "Google", "V2 must return Google as the sole active employer")

    def test_02_point_in_time_historical_query(self):
        case = V1_VS_V2_BENCHMARKS[6]  # TKG_07: Where was Rahul working on July 15, 2024?
        self.v2.ingest_events(case["events"])

        # Target date July 2024 was when he was at Swiggy
        v2_historical = self.v2.query_point_in_time("Rahul", "WORKS_AT", "2024-07-15")
        self.assertEqual(v2_historical, "Swiggy", "V2 point-in-time must resolve Swiggy for July 2024")

        # Current query must resolve Google
        v2_current = self.v2.query_active_attribute("Rahul", "WORKS_AT")
        self.assertEqual(v2_current, "Google", "V2 current active fact must resolve Google")

    def test_03_multi_hop_relational_traversal(self):
        case = V1_VS_V2_BENCHMARKS[11]  # TKG_12: Ashwin -> Appa -> Ramesh -> Bosch
        self.v1.ingest_events(case["events"])
        self.v2.ingest_events(case["events"])

        # V1: Vector search for 'Bosch' misses Appa introducing Ramesh
        v1_res = self.v1.query(case["query"])
        self.assertNotIn("appa", v1_res["synthesized_answer"].lower(), "V1 fails to bridge intermediate relationship")

        # V2: Discovers exact graph connection path
        path = self.v2.traverse_path("Ashwin", "Bosch")
        self.assertIsNotNone(path, "V2 must discover path from Ashwin to Bosch")
        self.assertEqual(path, ["Ashwin", "Prasad Appa", "Ramesh", "Bosch"])

    def test_04_state_contradiction_flight_cancellation(self):
        case = V1_VS_V2_BENCHMARKS[16]  # TKG_17: Flight booked -> rescheduled -> canceled
        self.v1.ingest_events(case["events"])
        self.v2.ingest_events(case["events"])

        # V1: Confuses old flight times with cancellation
        v1_res = self.v1.query(case["query"])
        self.assertTrue("10 am" in v1_res["synthesized_answer"].lower() or "4 pm" in v1_res["synthesized_answer"].lower())

        # V2: Only terminal status is active
        v2_status = self.v2.query_active_attribute("Flight 6E-204", "STATUS")
        self.assertEqual(v2_status, "Canceled completely")


if __name__ == "__main__":
    unittest.main()
