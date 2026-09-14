"""Comprehensive Unit Tests for Production GraphService (V2 Bitemporal Knowledge Graph).

Runs completely in-memory (DUCKDB_PATH=":memory:") to ensure zero file-locking
collisions with any running background Uvicorn server processes.
"""

import os
import sys
import unittest

# Crucial: Set in-memory DuckDB before any service imports
os.environ["DUCKDB_PATH"] = ":memory:"

# Ensure project root is on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.services.memory_service import MemoryService
from app.services.graph_service import GraphService


class TestGraphService(unittest.TestCase):
    def setUp(self):
        # Fresh in-memory DB per test class/run
        self.memory_svc = MemoryService(db_path=":memory:")
        self.graph_svc = GraphService(memory_svc=self.memory_svc)

    def test_entity_creation_and_resolution(self):
        """Tests case-insensitive entity resolution and alias linking."""
        ent1 = self.graph_svc.get_or_create_entity("Rahul", entity_type="Person", aliases=["Rahul Sharma"])
        self.assertEqual(ent1["name"], "Rahul")

        # Resolving same entity case-insensitively should return the exact same ID
        ent2 = self.graph_svc.get_or_create_entity("rahul")
        self.assertEqual(ent1["id"], ent2["id"])

        # Resolving via alias
        ent3 = self.graph_svc.get_or_create_entity("Rahul Sharma")
        self.assertEqual(ent1["id"], ent3["id"])

    def test_fact_assertion_and_terminal_invalidation(self):
        """Verifies the core V2 thesis: obsolete active facts are auto-closed (valid_to = valid_from)."""
        # Step 1: Rahul starts at Swiggy
        e1 = self.graph_svc.assert_fact(
            subject="Rahul",
            predicate="WORKS_AT",
            object="Swiggy",
            valid_from="2023-01-15",
            is_terminal_mutation=True
        )
        self.assertTrue(e1["is_active"])
        self.assertIsNone(e1["valid_to"])

        # Query active facts
        active_now = self.graph_svc.query_active_facts(subject="Rahul", predicate="WORKS_AT")
        self.assertEqual(len(active_now), 1)
        self.assertEqual(active_now[0]["object"], "Swiggy")

        # Step 2: 12 months later, Rahul moves to Google
        e2 = self.graph_svc.assert_fact(
            subject="Rahul",
            predicate="WORKS_AT",
            object="Google",
            valid_from="2024-01-15",
            is_terminal_mutation=True
        )
        self.assertTrue(e2["is_active"])
        self.assertIsNone(e2["valid_to"])

        # Query active facts now: must only be Google, NEVER both
        active_after = self.graph_svc.query_active_facts(subject="Rahul", predicate="WORKS_AT")
        self.assertEqual(len(active_after), 1)
        self.assertEqual(active_after[0]["object"], "Google")

        # Check history: Swiggy edge must have valid_to == '2024-01-15'
        history = self.graph_svc.query_entity_history("Rahul")
        self.assertEqual(len(history), 2)
        swiggy_edge = [h for h in history if h["object"] == "Swiggy"][0]
        self.assertEqual(swiggy_edge["valid_to"], "2024-01-15")

    def test_point_in_time_historical_queries(self):
        """Verifies bitemporal slice queries (valid_from <= T <= valid_to)."""
        self.graph_svc.assert_fact("Project Apex", "MANAGED_BY", "Priya", "2024-06-01")
        self.graph_svc.assert_fact("Project Apex", "MANAGED_BY", "Karthik", "2024-07-01")

        # Point in time: Mid June 2024 -> Must be Priya
        slice_june = self.graph_svc.query_point_in_time("2024-06-15", subject="Project Apex")
        self.assertEqual(len(slice_june), 1)
        self.assertEqual(slice_june[0]["object"], "Priya")

        # Point in time: Mid July 2024 -> Must be Karthik
        slice_july = self.graph_svc.query_point_in_time("2024-07-15", subject="Project Apex")
        self.assertEqual(len(slice_july), 1)
        self.assertEqual(slice_july[0]["object"], "Karthik")

    def test_multi_hop_bfs_traversal(self):
        """Verifies multi-hop relationship discovery across multiple entity hops."""
        # Chain: Ashwin -[COLLABORATES_WITH]-> Rachit -[CO_FOUNDER]-> Neha -[MENTORED_BY]-> Kunal Shah
        self.graph_svc.assert_fact("Ashwin", "COLLABORATES_WITH", "Rachit", "2024-01-01", is_terminal_mutation=False)
        self.graph_svc.assert_fact("Rachit", "CO_FOUNDER", "Neha", "2024-01-01", is_terminal_mutation=False)
        self.graph_svc.assert_fact("Neha", "MENTORED_BY", "Kunal Shah", "2024-01-01", is_terminal_mutation=False)

        path = self.graph_svc.traverse_network("Ashwin", "Kunal Shah", max_depth=4)
        self.assertIsNotNone(path)
        self.assertEqual(len(path), 3)
        self.assertEqual(path[0]["subject"], "Ashwin")
        self.assertEqual(path[0]["object"], "Rachit")
        self.assertEqual(path[1]["subject"], "Rachit")
        self.assertEqual(path[1]["object"], "Neha")
        self.assertEqual(path[2]["subject"], "Neha")
        self.assertEqual(path[2]["object"], "Kunal Shah")

    def test_flight_cancellation_contradiction(self):
        """Verifies state contradiction handling (booked -> rescheduled -> canceled)."""
        self.graph_svc.assert_fact("Flight 6E-204", "STATUS", "Scheduled for Friday 10 AM", "2024-08-01")
        self.graph_svc.assert_fact("Flight 6E-204", "STATUS", "Rescheduled to Friday 4 PM", "2024-08-05")
        self.graph_svc.assert_fact("Flight 6E-204", "STATUS", "Canceled completely", "2024-08-08")

        active = self.graph_svc.query_active_facts(subject="Flight 6E-204", predicate="STATUS")
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["object"], "Canceled completely")

    def test_natural_language_fact_extraction(self):
        """Verifies automated text parsing turns conversational messages into temporal edges."""
        statements = [
            ("Madhu joined Razorpay as an intern", "2024-01-10"),
            ("Madhu got promoted to full-time Backend Engineer at Razorpay", "2024-06-15"),
            ("Rachit lives in Chennai flat", "2023-01-01"),
            ("Rachit relocated to Bangalore", "2024-03-01"),
            ("Doctor changed metformin 500mg to metformin 1000mg twice daily", "2024-05-10"),
        ]

        for text, date_str in statements:
            self.graph_svc.extract_and_assert_from_text(text, date_str)

        # Madhu's role should be Full-Time Backend Engineer
        madhu_role = self.graph_svc.query_active_facts(subject="Madhu", predicate="HAS_ROLE")
        self.assertEqual(len(madhu_role), 1)
        self.assertEqual(madhu_role[0]["object"], "Full-Time Backend Engineer")

        # Rachit's city should be Bangalore
        rachit_city = self.graph_svc.query_active_facts(subject="Rachit", predicate="LIVES_IN")
        self.assertEqual(len(rachit_city), 1)
        self.assertEqual(rachit_city[0]["object"], "Bangalore")

        # Metformin dosage should be 1000mg
        metformin = self.graph_svc.query_active_facts(subject="Metformin", predicate="DOSAGE")
        self.assertEqual(len(metformin), 1)
        self.assertEqual(metformin[0]["object"], "1000mg twice daily")

    def test_llm_context_formatting(self):
        """Verifies prompt injection section generation with verified ground truth."""
        self.graph_svc.assert_fact("Rahul", "WORKS_AT", "Google", "2024-01-15")

        context = self.graph_svc.format_graph_context_for_query("Where does Rahul work?")
        self.assertIn("VERIFIED TEMPORAL KNOWLEDGE GRAPH", context)
        self.assertIn("Rahul", context)
        self.assertIn("Google", context)


if __name__ == "__main__":
    unittest.main()
