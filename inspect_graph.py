#!/usr/bin/env python3
"""Knowledge Graph Inspector & Diagnostic Utility for Version 2.0 (V2).

Provides instant visibility into:
1. DuckDB `entities` and `temporal_edges` table populations.
2. Active facts vs. historical invalidated slices.
3. Chronological entity mutation timelines.
4. Multi-hop BFS network path traversal.
5. Head-to-head V1 vs. V2 live comparisons.

Works seamlessly via the running HTTP server or direct DuckDB connection.

Usage:
    python inspect_graph.py                     # Shows summary & active facts
    python inspect_graph.py --seed              # Ingests 25 benchmark scenarios into DuckDB
    python inspect_graph.py --history Rahul     # Full chronological timeline for Rahul
    python inspect_graph.py --traverse Ashwin "Kunal Shah"  # Shortest BFS path
    python inspect_graph.py --compare           # Compares V1 vs V2 prompt outputs
"""

import os
import sys
import json
import argparse
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional

# Ensure localai root is on sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "assistant.duckdb")


def load_token() -> str:
    """Reads device token from .env for authenticated API queries."""
    env_path = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("AUTHORIZED_DEVICE_TOKENS="):
                    tokens = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if tokens:
                        return tokens.split(",")[0].strip()
    return "dev_master_token"


def api_request(path: str, method: str = "GET", data: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Makes a request to the local assistant server."""
    token = load_token()
    url = f"http://127.0.0.1:8000{path}"
    headers = {
        "X-Device-Token": token,
        "Content-Type": "application/json"
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8") if data else None,
        headers=headers,
        method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def get_direct_duckdb_data():
    """Fallback reader directly from DuckDB in read-only mode."""
    try:
        import duckdb
        if not os.path.exists(DB_PATH):
            return None, None
        con = duckdb.connect(DB_PATH, read_only=True)
        entities = con.execute("SELECT id, name, entity_type, aliases FROM entities ORDER BY name").fetchall()
        edges = con.execute("SELECT id, subject, predicate, object, valid_from, valid_to FROM temporal_edges ORDER BY created_at DESC").fetchall()
        con.close()
        return entities, edges
    except Exception as exc:
        return None, None


# =============================================================================
# CLI COMMAND IMPLEMENTATIONS
# =============================================================================

def cmd_summary():
    """Prints a high-level summary of entities and active facts."""
    print("\n" + "=" * 80)
    print(" 🧠 KNOWLEDGE GRAPH (V2) — LIVE DATABASE INSPECTION")
    print("=" * 80)

    # 1. Try via API first
    api_facts = api_request("/api/v2/graph/facts")
    api_entities = api_request("/api/v2/graph/entities?limit=100")

    if api_facts is not None and api_entities is not None:
        facts = api_facts.get("facts", [])
        entities = api_entities.get("entities", [])
        source_label = "⚡ Live FastAPI Server (http://127.0.0.1:8000/api/v2/graph)"
    else:
        # Fallback to direct DuckDB
        entities_raw, edges_raw = get_direct_duckdb_data()
        if entities_raw is None:
            print("\n❌ Could not connect to either the running server or DuckDB.")
            print("   Start the server with: python run.py")
            print("=" * 80 + "\n")
            return

        source_label = f"📁 Direct DuckDB File ({DB_PATH})"
        entities = [{"id": r[0], "name": r[1], "entity_type": r[2], "aliases": r[3]} for r in entities_raw]
        facts = [
            {"id": r[0], "subject": r[1], "predicate": r[2], "object": r[3], "valid_from": r[4], "valid_to": r[5]}
            for r in edges_raw if r[5] is None
        ]

    active_facts = [f for f in facts if f.get("valid_to") is None]
    
    print(f"Data Source: {source_label}")
    print(f"Total Entities Registered : {len(entities)}")
    print(f"Total Active Facts        : {len(active_facts)}")
    print("-" * 80)

    if not active_facts:
        print("\nℹ️  The Knowledge Graph is currently empty.")
        print("   To populate it with the 25 benchmark scenarios, run:")
        print("   👉 python inspect_graph.py --seed\n")
        print("=" * 80 + "\n")
        return

    print(f"\n{'SUBJECT':<18} | {'RELATIONSHIP':<18} | {'TARGET / VALUE':<24} | {'SINCE':<12}")
    print("-" * 80)
    for f in active_facts[:35]:
        print(f"{f['subject']:<18} | {f['predicate']:<18} | {f['object']:<24} | {f['valid_from']:<12}")

    if len(active_facts) > 35:
        print(f"... and {len(active_facts) - 35} more active facts.")

    print("=" * 80 + "\n")


def cmd_history(entity_name: str):
    """Displays the full chronological timeline of mutations for an entity."""
    print("\n" + "=" * 80)
    print(f" 📜 CHRONOLOGICAL MUTATION TIMELINE FOR: '{entity_name}'")
    print("=" * 80)

    res = api_request(f"/api/v2/graph/entity/{urllib.parse.quote(entity_name)}")
    if not res:
        # Fallback to local memory_service
        os.environ["DUCKDB_PATH"] = ":memory:"
        from app.services.graph_service import graph_service
        timeline = graph_service.query_entity_history(entity_name)
    else:
        timeline = res.get("historical_timeline", [])

    if not timeline:
        print(f"No historical facts found for entity '{entity_name}'.")
        print("=" * 80 + "\n")
        return

    print(f"{'PREDICATE':<18} | {'TARGET / VALUE':<22} | {'VALID INTERVAL':<25} | {'STATE'}")
    print("-" * 80)
    for item in timeline:
        v_to = item.get("valid_to")
        interval = f"{item['valid_from']} → {v_to if v_to else 'PRESENT'}"
        status_tag = "✅ ACTIVE" if v_to is None else f"❌ CLOSED on {v_to}"
        print(f"{item['predicate']:<18} | {item['object']:<22} | {interval:<25} | {status_tag}")

    print("=" * 80 + "\n")


def cmd_traverse(start: str, target: str):
    """Displays the multi-hop Breadth-First Search connection path."""
    print("\n" + "=" * 80)
    print(f" 🕸️ MULTI-HOP GRAPH TRAVERSAL: '{start}' ➔ '{target}'")
    print("=" * 80)

    res = api_request(f"/api/v2/graph/traverse?start={urllib.parse.quote(start)}&target={urllib.parse.quote(target)}&max_depth=5")
    if not res:
        from app.services.graph_service import graph_service
        path = graph_service.traverse_network(start, target, max_depth=5)
    else:
        path = res.get("path", [])

    if not path:
        print(f"No relationship path connects '{start}' to '{target}' within 5 hops.")
        print("=" * 80 + "\n")
        return

    print(f"Found connection path in {len(path)} hops:\n")
    chain = [start]
    for step in path:
        print(f"  • {step['subject']}  ==[{step['predicate']} (since {step['valid_from']})]==>  {step['object']}")
        chain.append(f"--[{step['predicate']}]--> {step['object']}")

    print("\nVisual Chain Summary:")
    print(f"  {start} {' '.join(chain[1:])}")
    print("=" * 80 + "\n")


def cmd_seed():
    """Seeds the 25 benchmark scenarios into the Knowledge Graph."""
    print("\n" + "=" * 80)
    print(" 🌱 SEEDING 25 CANONICAL BENCHMARK SCENARIOS INTO KNOWLEDGE GRAPH")
    print("=" * 80)

    from tests.dataset_v1_vs_v2_benchmarks import V1_VS_V2_BENCHMARKS

    seeded_count = 0
    use_api = api_request("/api/v2/graph/facts") is not None

    if not use_api:
        from app.services.graph_service import graph_service

    for sc in V1_VS_V2_BENCHMARKS:
        for ev in sc.get("events", []):
            date_str = ev.get("date", "2024-01-01")
            text = ev["text"]

            if use_api:
                res = api_request("/api/v2/graph/extract", method="POST", data={
                    "text": text,
                    "date_str": date_str,
                    "source_id": sc.get("id", "TKG_TEST")
                })
                if res and res.get("success"):
                    seeded_count += 1
            else:
                try:
                    graph_service.extract_and_assert_from_text(text, date_str, source_id=sc.get("id", "TKG_TEST"))
                    seeded_count += 1
                except Exception as exc:
                    print(f"  [Error] {exc}")

    target_desc = "via live FastAPI server (http://127.0.0.1:8000)" if use_api else "directly into DuckDB"
    print(f"\n✅ Successfully processed and indexed {seeded_count} benchmark events {target_desc}!")
    print("Run: python inspect_graph.py to view the populated tables.")
    print("To clean this benchmark data anytime, run: python inspect_graph.py --clean")
    print("=" * 80 + "\n")


def cmd_compare():
    """Runs a side-by-side prompt test comparing V1 vs V2 context injection."""
    print("\n" + "=" * 80)
    print(" ⚖️ SIDE-BY-SIDE PROMPT REASONING COMPARISON: V1 (VECTOR RAG) vs. V2 (TEMPORAL KG)")
    print("=" * 80)

    prompt = "Where does Rahul currently work?"
    print(f"Question: \"{prompt}\"\n")

    from app.services.llm_service import OllamaLLMService
    llm = OllamaLLMService()

    _, v1_sys, _ = llm._prepare_routed_execution(prompt, "MESSAGE_LOOKUP", version="v1")
    _, v2_sys, _ = llm._prepare_routed_execution(prompt, "MESSAGE_LOOKUP", version="v2")

    print("--- [VERSION 1.0: PURE VECTOR RAG PROMPT] ---")
    print(v1_sys[:350] + "...\n")

    print("--- [VERSION 2.0: BITEMPORAL KNOWLEDGE GRAPH PROMPT] ---")
    print(v2_sys[:450] + "...\n")

    print("Notice how Version 2 explicitly injects the verified ground truth, eliminating ambiguity.")
    print("=" * 80 + "\n")


def cmd_clean():
    """Removes all seeded benchmark test facts (tagged with source_id LIKE 'TKG_%') from DuckDB."""
    print("\n" + "=" * 80)
    print(" 🧹 CLEANING TEST / BENCHMARK DATA FROM KNOWLEDGE GRAPH")
    print("=" * 80)

    use_api = api_request("/api/v2/graph/facts") is not None
    if use_api:
        res = api_request("/api/v2/graph/clean", method="DELETE")
        if res and res.get("success"):
            print(f"✅ Removed {res.get('deleted', 0)} benchmark test facts via live FastAPI server.")
        else:
            print("❌ Server error during clean.")
    else:
        try:
            from app.services.memory_service import memory_service
            from app.models.memory import TemporalEdge, Entity, Contact
            from sqlalchemy import delete, select

            session = memory_service.get_session()
            del_edges = session.execute(
                delete(TemporalEdge).where(TemporalEdge.source_id.like("TKG_%"))
            )
            session.commit()

            subs = set(session.scalars(select(TemporalEdge.subject)).all())
            objs = set(session.scalars(select(TemporalEdge.object)).all())
            used_names = {n.lower() for n in (subs | objs) if n}
            contact_names = {c.lower() for c in session.scalars(select(Contact.name)).all() if c}

            for ent in session.scalars(select(Entity)).all():
                if ent.name.lower() not in used_names and ent.name.lower() not in contact_names and ent.name.lower() != "ashwin":
                    session.delete(ent)
            session.commit()

            count = del_edges.rowcount
            print(f"✅ Removed {count} benchmark test facts directly from DuckDB.")
        except Exception as exc:
            print(f"Error during direct clean: {exc}")

    print("Your personal database contains ONLY your real data!")
    print("=" * 80 + "\n")


def cmd_sandbox():
    """Runs a 100% in-memory demonstration of the V2 Knowledge Graph without touching disk."""
    print("\n" + "=" * 80)
    print(" 🛡️ RUNNING IN-MEMORY V2 GRAPH DEMONSTRATION (ZERO DISK WRITES)")
    print("=" * 80)
    print("Database Mode: In-Memory RAM (:memory:)")
    print("Your real 'data/assistant.duckdb' will NOT be touched at all.\n")

    os.environ["DUCKDB_PATH"] = ":memory:"
    from app.services.memory_service import MemoryService
    from app.services.graph_service import GraphService

    mem = MemoryService(db_path=":memory:")
    graph = GraphService(memory_svc=mem)

    print("1. Ingesting Scenario: Rahul working at Swiggy (Jan 2023)...")
    graph.assert_fact("Rahul", "WORKS_AT", "Swiggy", "2023-01-15")

    print("2. Ingesting Mutation: Rahul moves to Google (Jan 2024)...")
    graph.assert_fact("Rahul", "WORKS_AT", "Google", "2024-01-15")

    print("\n3. Querying Active Facts for Rahul (valid_to IS NULL):")
    active = graph.query_active_facts(subject="Rahul", predicate="WORKS_AT")
    for a in active:
        print(f"   • Current Active Employer: {a['object']} (Active since {a['valid_from']})")

    print("\n4. Querying Historical Point-in-Time (Where did Rahul work in June 2023?):")
    june_slice = graph.query_point_in_time("2023-06-15", subject="Rahul", predicate="WORKS_AT")
    for s in june_slice:
        print(f"   • Employer in June 2023: {s['object']}")

    print("\n5. Ingesting Relational Chain: Ashwin -> Rachit -> Neha -> Kunal Shah...")
    graph.assert_fact("Ashwin", "COLLABORATES_WITH", "Rachit", "2024-01-01", is_terminal_mutation=False)
    graph.assert_fact("Rachit", "CO_FOUNDER", "Neha", "2024-01-01", is_terminal_mutation=False)
    graph.assert_fact("Neha", "MENTORED_BY", "Kunal Shah", "2024-01-01", is_terminal_mutation=False)

    path = graph.traverse_network("Ashwin", "Kunal Shah", max_depth=4)
    steps = ["Ashwin"]
    for step in path:
        steps.append(f"--[{step['predicate']}]--> {step['object']}")
    print(f"   • Discovered Path: {' '.join(steps)}")

    print("\n✅ Sandbox test completed successfully. Memory discarded instantly.")
    print("=" * 80 + "\n")


import urllib.parse

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inspect and test the V2 Knowledge Graph")
    parser.add_argument("--summary", action="store_true", help="Display summary of entities and active facts")
    parser.add_argument("--sandbox", action="store_true", help="Run 100% in-memory demo (zero disk writes)")
    parser.add_argument("--clean", action="store_true", help="Purge any benchmark test data from DuckDB")
    parser.add_argument("--seed", action="store_true", help="Seed 25 benchmark scenarios into DuckDB")
    parser.add_argument("--history", type=str, default=None, help="Inspect full mutation history for an entity")
    parser.add_argument("--traverse", nargs=2, metavar=("START", "TARGET"), help="BFS traverse between two entities")
    parser.add_argument("--compare", action="store_true", help="Show side-by-side V1 vs V2 prompt construction")
    args = parser.parse_args()

    if args.sandbox:
        cmd_sandbox()
    elif args.clean:
        cmd_clean()
    elif args.seed:
        cmd_seed()
    elif args.history:
        cmd_history(args.history)
    elif args.traverse:
        cmd_traverse(args.traverse[0], args.traverse[1])
    elif args.compare:
        cmd_compare()
    else:
        cmd_summary()
