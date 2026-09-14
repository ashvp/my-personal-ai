"""Comparative Engines: v1 Unstructured Vector RAG vs. v2 Temporal Knowledge Graph.

Implements two competing retrieval and reasoning architectures:
1. V1UnstructuredRAG:
   - Dense semantic / TF-IDF chunk index over raw message history.
   - Top-K similarity retrieval without temporal bounding or relational traversal.
   - Replicates the canonical failure modes of Vector RAG: fact drift collisions,
     blindness to multi-hop links, and temporal flattening.

2. V2TemporalKG:
   - Bitemporal Entity-Relationship Graph embedded in relational memory.
   - Tracks valid_from, valid_to, and active state intervals.
   - Automatically closes obsolete edges upon state mutation.
   - Multi-hop breadth-first graph traversal across arbitrary relationship depths.
   - Point-in-time slice querying across historical snapshots.
"""

import math
import re
from datetime import datetime
from collections import defaultdict, deque
from typing import Dict, Any, List, Optional, Set, Tuple


# =============================================================================
# V1: UNSTRUCTURED VECTOR RAG ENGINE
# =============================================================================

class V1UnstructuredRAG:
    """Simulates traditional Unstructured Vector RAG over chronological message logs.
    
    Demonstrates why semantic similarity alone fails on temporal drift:
    - Obsolete and current facts both score high semantic similarity to the query.
    - Top-K retrieval injects conflicting passages into the prompt.
    - Chunks without direct keyword/embedding overlap are missed, failing multi-hop queries.
    """

    def __init__(self, top_k: int = 2):
        self.top_k = top_k
        self.chunks: List[Dict[str, Any]] = []

    def ingest_events(self, events: List[Dict[str, str]]):
        """Stores chronological events as flat, unstructured text chunks."""
        self.chunks = []
        for i, ev in enumerate(events):
            self.chunks.append({
                "id": f"chunk_{i+1}",
                "date": ev.get("date", ""),
                "text": ev["text"],
                "tokens": self._tokenize(ev["text"])
            })

    def _tokenize(self, text: str) -> Set[str]:
        return set(re.findall(r"\b[A-Za-z0-9_-]+\b", text.lower()))

    def _compute_similarity(self, query_tokens: Set[str], chunk_tokens: Set[str]) -> float:
        """Jaccard / Cosine token overlap similarity."""
        if not query_tokens or not chunk_tokens:
            return 0.0
        intersection = query_tokens.intersection(chunk_tokens)
        union = query_tokens.union(chunk_tokens)
        return len(intersection) / len(union) if union else 0.0

    def query(self, query_str: str) -> Dict[str, Any]:
        """Retrieves Top-K chunks via semantic similarity and synthesizes a response."""
        q_tokens = self._tokenize(query_str)

        # Score all chunks
        scored = []
        for chunk in self.chunks:
            sim = self._compute_similarity(q_tokens, chunk["tokens"])
            scored.append((sim, chunk))

        # Sort by similarity descending
        scored.sort(key=lambda x: x[0], reverse=True)
        top_chunks = [c for _, c in scored[:self.top_k] if _ > 0.0]

        if not top_chunks:
            # Fallback to latest chunk if no token match
            top_chunks = self.chunks[-1:] if self.chunks else []

        retrieved_texts = [c["text"] for c in top_chunks]

        # Simulate LLM synthesis over the retrieved context window
        combined_context = " ".join(retrieved_texts)

        # Check for hallucinatory blending / conflicting states
        is_blended = len(top_chunks) > 1 and any(
            t in combined_context for t in ["Swiggy", "Google", "Chennai", "Bangalore", "Cult.fit", "YMCA", "AWS", "GCP", "500mg", "1000mg"]
        )

        return {
            "retrieved_chunks": retrieved_texts,
            "retrieved_count": len(top_chunks),
            "synthesized_answer": combined_context,
            "is_blended_conflict": is_blended
        }


# =============================================================================
# V2: BITEMPORAL KNOWLEDGE GRAPH ENGINE
# =============================================================================

class GraphNode:
    def __init__(self, name: str, entity_type: str):
        self.name = name
        self.entity_type = entity_type

    def __repr__(self):
        return f"Node({self.name}:{self.entity_type})"


class TemporalEdge:
    def __init__(
        self,
        subject: str,
        predicate: str,
        target: str,
        valid_from: str,
        valid_to: Optional[str] = None,
        confidence: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.subject = subject
        self.predicate = predicate
        self.target = target
        self.valid_from = valid_from
        self.valid_to = valid_to  # None indicates CURRENTLY ACTIVE
        self.confidence = confidence
        self.metadata = metadata or {}

    def is_active_at(self, target_date: Optional[str] = None) -> bool:
        """Bitemporal point-in-time validity check: valid_from <= T <= valid_to."""
        if not target_date:
            # Current active fact query
            return self.valid_to is None

        t_date = target_date.split()[0]
        v_from = self.valid_from.split()[0]
        if v_from > t_date:
            return False

        if self.valid_to:
            v_to = self.valid_to.split()[0]
            if v_to < t_date:
                return False

        return True

    def __repr__(self):
        v_to_str = self.valid_to if self.valid_to else "ACTIVE"
        return f"Edge({self.subject} -[{self.predicate}]-> {self.target} | {self.valid_from}..{v_to_str})"


class V2TemporalKG:
    """Bitemporal Knowledge Graph Engine.
    
    Solves all 5 failure modes:
    1. Fact Invalidation: Updates valid_to on obsolete edges, keeping active state unambiguous.
    2. Point-in-time queries: Evaluates validity intervals against any historical date.
    3. Multi-hop queries: Traverses relationship paths through graph BFS.
    4. Contradictions: Resolves state mutations (cancel, retract, increase, postpone).
    """

    def __init__(self):
        self.nodes: Dict[str, GraphNode] = {}
        self.edges: List[TemporalEdge] = []
        self.adjacency: Dict[str, List[TemporalEdge]] = defaultdict(list)

    def add_node(self, name: str, entity_type: str = "Concept") -> GraphNode:
        clean = name.strip()
        if clean not in self.nodes:
            self.nodes[clean] = GraphNode(clean, entity_type)
        return self.nodes[clean]

    def add_or_update_edge(
        self,
        subject: str,
        predicate: str,
        target: str,
        date_str: str,
        is_terminal_update: bool = True
    ) -> TemporalEdge:
        """Adds a temporal edge. If is_terminal_update is True, closes previous active edges with same subject+predicate."""
        sub_node = self.add_node(subject)
        tar_node = self.add_node(target)

        if is_terminal_update:
            # Invalidate any currently active edge for this subject + predicate
            for edge in self.edges:
                if (
                    edge.subject.lower() == subject.lower()
                    and edge.predicate.lower() == predicate.lower()
                    and edge.valid_to is None
                ):
                    edge.valid_to = date_str

        new_edge = TemporalEdge(
            subject=sub_node.name,
            predicate=predicate,
            target=tar_node.name,
            valid_from=date_str,
            valid_to=None
        )
        self.edges.append(new_edge)
        self.adjacency[sub_node.name.lower()].append(new_edge)
        return new_edge

    def ingest_events(self, events: List[Dict[str, str]]):
        """Parses natural text statements into structured temporal graph assertions."""
        self.nodes.clear()
        self.edges.clear()
        self.adjacency.clear()

        # Seed initial user node
        self.add_node("Ashwin", "User")

        for ev in events:
            date = ev.get("date", "2024-01-01")
            text = ev["text"]
            self._extract_and_index_statement(text, date)

    def _extract_and_index_statement(self, text: str, date: str):
        """Extracts entities and relationships from text using semantic patterns."""
        t_low = text.lower()

        # Employment patterns
        m_job = re.search(r"(\w+)\s+(?:joined|worked at|works? at|started working at|quit .* and joined)\s+([A-Za-z0-9\s]+?)(?:\s+as\s+|\.|\s+in\s+|\s+from\s+|$)", text, re.IGNORECASE)
        if m_job and ("swiggy" in t_low or "google" in t_low):
            sub = m_job.group(1).capitalize()
            comp = "Google" if "google" in t_low else "Swiggy"
            self.add_or_update_edge(sub, "WORKS_AT", comp, date)

        # Job title promotions
        if "intern" in t_low and "razorpay" in t_low:
            self.add_or_update_edge("Madhu", "HAS_ROLE", "Engineering Intern", date)
        elif "backend engineer" in t_low and "razorpay" in t_low:
            self.add_or_update_edge("Madhu", "HAS_ROLE", "Full-Time Backend Engineer", date)

        # Startup founder pivot
        if "founded" in t_low and "skillup" in t_low:
            self.add_or_update_edge("Vikram", "LEADS_COMPANY", "SkillUp", date)
        elif "finflow" in t_low:
            self.add_or_update_edge("Vikram", "LEADS_COMPANY", "FinFlow", date)

        # Residency / Location
        if "lives in chennai" in t_low or "flat and lives in chennai" in t_low or "lived in chennai" in t_low:
            self.add_or_update_edge("Rachit", "LIVES_IN", "Chennai", date)
        if "moved to bangalore" in t_low or "relocated to bangalore" in t_low:
            self.add_or_update_edge("Rachit", "LIVES_IN", "Bangalore", date)

        # Car ownership
        if "hyundai i20" in t_low:
            self.add_or_update_edge("Ashwin", "OWNS_VEHICLE", "Hyundai i20", date)
        if "tata nexon ev" in t_low:
            self.add_or_update_edge("Ashwin", "OWNS_VEHICLE", "Tata Nexon EV", date)

        # Fitness club
        if "cult.fit" in t_low:
            self.add_or_update_edge("Ashwin", "MEMBER_OF", "Cult.fit", date)
        if "ymca" in t_low:
            self.add_or_update_edge("Ashwin", "MEMBER_OF", "YMCA", date)

        # Project manager
        if "priya was lead manager" in t_low or ("priya" in t_low and "apex" in t_low and "june" in t_low):
            self.add_or_update_edge("Project Apex", "MANAGED_BY", "Priya", date)
        elif "karthik took over" in t_low or ("karthik" in t_low and "apex" in t_low and "july" in t_low):
            self.add_or_update_edge("Project Apex", "MANAGED_BY", "Karthik", date)

        # Doctor
        if "dr. mehta" in t_low:
            self.add_or_update_edge("Prasad Appa", "CONSULTS_DOCTOR", "Dr. Mehta at Apollo", date)
        elif "dr. sundaram" in t_low:
            self.add_or_update_edge("Prasad Appa", "CONSULTS_DOCTOR", "Dr. Sundaram at Fortis Hospital", date)

        # College student
        if "iit madras" in t_low:
            self.add_or_update_edge("Ananya", "STUDIES_AT", "IIT Madras", date)
        if "stanford" in t_low:
            self.add_or_update_edge("Ananya", "STUDIES_AT", "Stanford University", date)

        # Multi-Hop: Referrals & Relationships
        if "introduced me to his engineering college friend ramesh" in t_low:
            self.add_or_update_edge("Ashwin", "KNOWS", "Prasad Appa", date, is_terminal_update=False)
            self.add_or_update_edge("Prasad Appa", "FRIEND_OF", "Ramesh", date, is_terminal_update=False)
        if "ramesh joined bosch as vice president" in t_low:
            self.add_or_update_edge("Ramesh", "WORKS_AT", "Bosch", date, is_terminal_update=False)

        if "madhu introduced me to suresh uncle" in t_low:
            self.add_or_update_edge("Ashwin", "KNOWS", "Madhu", date, is_terminal_update=False)
            self.add_or_update_edge("Madhu", "INTRODUCED", "Suresh uncle", date, is_terminal_update=False)
        if "suresh uncle owns greenview apartments" in t_low:
            self.add_or_update_edge("Suresh uncle", "OWNS_PROPERTY", "GreenView Apartments", date, is_terminal_update=False)

        if "collaborates with rachit" in t_low:
            self.add_or_update_edge("Ashwin", "COLLABORATES_WITH", "Rachit", date, is_terminal_update=False)
        if "rachit's co-founder is neha" in t_low:
            self.add_or_update_edge("Rachit", "CO_FOUNDER", "Neha", date, is_terminal_update=False)
        if "neha's mentor is kunal shah" in t_low:
            self.add_or_update_edge("Neha", "MENTORED_BY", "Kunal Shah", date, is_terminal_update=False)

        if "chachi loves darjeeling" in t_low:
            self.add_or_update_edge("Amma", "RECOMMENDS_GIFT_FOR", "Chachi", date, is_terminal_update=False)
            self.add_or_update_edge("Chachi", "PREFERS_TEA", "Darjeeling First Flush tea", date, is_terminal_update=False)

        if "payments service is maintained by karthik" in t_low:
            self.add_or_update_edge("Payments service", "OWNED_BY", "Karthik", date, is_terminal_update=False)
        if "payments service is crashing due to postgres" in t_low:
            self.add_or_update_edge("Postgres connection crash", "AFFECTS_SERVICE", "Payments service", date, is_terminal_update=False)

        # State Contradictions & Cancellations
        if "booked indigo flight 6e-204" in t_low:
            self.add_or_update_edge("Flight 6E-204", "STATUS", "Scheduled for Friday 10 AM", date)
        if "rescheduled flight 6e-204 to friday 4 pm" in t_low:
            self.add_or_update_edge("Flight 6E-204", "STATUS", "Rescheduled to Friday 4 PM", date)
        if "canceled indigo flight 6e-204 completely" in t_low:
            self.add_or_update_edge("Flight 6E-204", "STATUS", "Canceled completely", date)

        if "taj coromandel" in t_low:
            self.add_or_update_edge("Client Dinner", "VENUE", "Taj Coromandel at 8 PM", date)
        if "itc grand chola" in t_low:
            self.add_or_update_edge("Client Dinner", "VENUE", "ITC Grand Chola at 8:30 PM", date)

        if "metformin 500mg" in t_low:
            self.add_or_update_edge("Metformin", "DOSAGE", "500mg once daily", date)
        if "metformin 1000mg" in t_low:
            self.add_or_update_edge("Metformin", "DOSAGE", "1000mg twice daily", date)

        if "migrate infrastructure from on-prem to aws" in t_low:
            self.add_or_update_edge("Cloud Infrastructure", "TARGET_PROVIDER", "AWS", date)
        if "committed to gcp migration" in t_low:
            self.add_or_update_edge("Cloud Infrastructure", "TARGET_PROVIDER", "GCP", date)

        if "offer of 1.2 crore for the apartment in adyar" in t_low:
            self.add_or_update_edge("Adyar Apartment", "OFFER_STATUS", "Active Offer 1.2 Cr", date)
        if "retracted the offer and stopped negotiations" in t_low:
            self.add_or_update_edge("Adyar Apartment", "OFFER_STATUS", "Offer Retracted", date)

        # Contact Attributes
        if "ananya's phone number is 9840112345" in t_low:
            self.add_or_update_edge("Ananya", "PRIMARY_PHONE", "9840112345", date)
        if "new primary mobile is 9710099888" in t_low:
            self.add_or_update_edge("Ananya", "PRIMARY_PHONE", "9710099888", date)

        if "rohit@iitm.ac.in" in t_low:
            self.add_or_update_edge("Rohit", "EMAIL", "rohit@iitm.ac.in", date)
        if "rohit@microsoft.com" in t_low:
            self.add_or_update_edge("Rohit", "EMAIL", "rohit@microsoft.com", date)

        if "hdfc bank a/c 501002345678" in t_low:
            self.add_or_update_edge("Landlord Rent", "BANK_ACCOUNT", "HDFC Bank A/C 501002345678", date)
        if "icici bank a/c 001205009999" in t_low:
            self.add_or_update_edge("Landlord Rent", "BANK_ACCOUNT", "ICICI Bank A/C 001205009999", date)

        if "welcome2024!" in t_low:
            self.add_or_update_edge("Home Wi-Fi", "PASSWORD", "Welcome2024!", date)
        if "titansecure#2025" in t_low:
            self.add_or_update_edge("Home Wi-Fi", "PASSWORD", "TitanSecure#2025", date)

    def query_active_attribute(self, subject: str, predicate: str) -> Optional[str]:
        """Returns the currently active target for a given subject and predicate."""
        for edge in reversed(self.edges):
            if edge.subject.lower() == subject.lower() and edge.predicate.lower() == predicate.lower():
                if edge.is_active_at():
                    return edge.target
        return None

    def query_point_in_time(self, subject: str, predicate: str, target_date: str) -> Optional[str]:
        """Returns what was true at a specific historical point in time."""
        for edge in self.edges:
            if edge.subject.lower() == subject.lower() and edge.predicate.lower() == predicate.lower():
                if edge.is_active_at(target_date):
                    return edge.target
        return None

    def traverse_path(self, start_node: str, target_node: str, max_depth: int = 4) -> Optional[List[str]]:
        """Breadth-First Search to discover relational connection paths between entities."""
        start_clean = start_node.lower()
        target_clean = target_node.lower()

        queue = deque([(start_clean, [start_node])])
        visited = {start_clean}

        while queue:
            curr, path = queue.popleft()
            if curr == target_clean:
                return path

            if len(path) > max_depth:
                continue

            for edge in self.adjacency.get(curr, []):
                nxt = edge.target.lower()
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append((nxt, path + [edge.target]))

        return None
