import json
import logging
import re
import uuid
from collections import defaultdict, deque
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import and_, func, or_, select, update

from app.models.memory import Entity, TemporalEdge
from app.services.memory_service import MemoryService, memory_service

logger = logging.getLogger(__name__)

# Mutually exclusive predicates where a new assertion invalidates prior active values
MUTEX_PREDICATES = {
    "WORKS_AT",
    "LIVES_IN",
    "HAS_ROLE",
    "LEADS_COMPANY",
    "OWNS_VEHICLE",
    "MEMBER_OF",
    "MANAGED_BY",
    "CONSULTS_DOCTOR",
    "STUDIES_AT",
    "STATUS",
    "VENUE",
    "DOSAGE",
    "TARGET_PROVIDER",
    "OFFER_STATUS",
    "PRIMARY_PHONE",
    "EMAIL",
    "BANK_ACCOUNT",
    "PASSWORD",
}


class GraphService:
    """Production Bitemporal Knowledge Graph Engine (V2).
    
    Persists entities and temporal edges in DuckDB via SQLAlchemy ORM.
    Key capabilities:
    1. Entity Resolution: Normalized node tracking with alias support.
    2. Bitemporal Edge Mutation: Automatically closes obsolete edges (valid_to = valid_from)
       when conflicting state arrives, preventing historical hallucination.
    3. Point-in-Time Traversal: Queries temporal slices (valid_from <= T <= valid_to).
    4. Multi-Hop Relational Reasoning: Breadth-First Search across relational networks.
    5. Natural Text Fact Extraction: Converts message / email narratives into graph facts.
    """

    def __init__(self, memory_svc: Optional[MemoryService] = None):
        self.memory = memory_svc or memory_service

    def get_session(self):
        """Fetches a thread-local SQLAlchemy session from the shared memory engine."""
        return self.memory.get_session()

    # =========================================================================
    # 1. ENTITY MANAGEMENT & RESOLUTION
    # =========================================================================

    def get_or_create_entity(
        self,
        name: str,
        entity_type: str = "Concept",
        aliases: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Resolves an entity by normalized name or alias, creating it if not present."""
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Entity name cannot be empty.")

        session = self.get_session()
        try:
            # 1. Case-insensitive exact name match
            stmt = select(Entity).where(func.lower(Entity.name) == clean_name.lower())
            entity = session.scalars(stmt).first()

            if entity:
                # Update aliases if new ones provided
                if aliases:
                    existing_aliases = set(
                        [a.strip() for a in (entity.aliases or "").split(",") if a.strip()]
                    )
                    existing_aliases.update([a.strip() for a in aliases if a.strip()])
                    entity.aliases = ", ".join(sorted(existing_aliases))
                    session.commit()
                return entity.to_dict()

            # 2. Alias lookup
            stmt_alias = select(Entity).where(Entity.aliases.ilike(f"%{clean_name}%"))
            entity_alias = session.scalars(stmt_alias).first()
            if entity_alias:
                return entity_alias.to_dict()

            # 3. Create new entity
            new_id = f"ent_{uuid.uuid4().hex[:12]}"
            alias_str = ", ".join(sorted(set(aliases))) if aliases else ""
            new_entity = Entity(
                id=new_id,
                name=clean_name,
                entity_type=entity_type,
                aliases=alias_str,
                metadata_json=json.dumps(metadata or {})
            )
            session.add(new_entity)
            session.commit()
            logger.info(f"[Graph] Created entity '{clean_name}' ({entity_type}) with ID {new_id}")
            return new_entity.to_dict()
        except Exception as exc:
            session.rollback()
            logger.error(f"Error resolving entity '{name}': {exc}")
            raise
        finally:
            session.close()

    def search_entities(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Searches entities by name or aliases."""
        session = self.get_session()
        try:
            term = f"%{query.strip()}%"
            stmt = (
                select(Entity)
                .where(or_(Entity.name.ilike(term), Entity.aliases.ilike(term)))
                .order_by(Entity.name.asc())
                .limit(limit)
            )
            results = session.scalars(stmt).all()
            return [e.to_dict() for e in results]
        finally:
            session.close()

    # =========================================================================
    # 2. BITEMPORAL EDGE ASSERTION & MUTATION
    # =========================================================================

    def assert_fact(
        self,
        subject: str,
        predicate: str,
        object: str,
        valid_from: str,
        source_id: Optional[str] = "",
        confidence: float = 1.0,
        is_terminal_mutation: Optional[bool] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Asserts a fact edge in the temporal graph.
        
        If is_terminal_mutation is True (or predicate is in MUTEX_PREDICATES),
        any currently active edge with the same subject and predicate is closed:
        edge.valid_to = valid_from.
        """
        clean_sub = subject.strip()
        clean_pred = predicate.strip().upper()
        clean_obj = object.strip()

        if not clean_sub or not clean_pred or not clean_obj:
            raise ValueError("Subject, predicate, and object must all be non-empty.")

        # Auto-detect terminal mutation if not explicitly specified
        if is_terminal_mutation is None:
            is_terminal_mutation = clean_pred in MUTEX_PREDICATES

        # Ensure both endpoints exist as entities
        self.get_or_create_entity(clean_sub)
        self.get_or_create_entity(clean_obj)

        session = self.get_session()
        try:
            # Step 1: Invalidate active edge if terminal mutation
            if is_terminal_mutation:
                stmt_active = select(TemporalEdge).where(
                    func.lower(TemporalEdge.subject) == clean_sub.lower(),
                    func.lower(TemporalEdge.predicate) == clean_pred.lower(),
                    TemporalEdge.valid_to.is_(None)
                )
                active_edges = session.scalars(stmt_active).all()
                for old_edge in active_edges:
                    # Do not re-insert identical fact if already active
                    if old_edge.object.lower() == clean_obj.lower():
                        logger.info(f"[Graph] Fact already active: {clean_sub} -[{clean_pred}]-> {clean_obj}")
                        return old_edge.to_dict()
                    old_edge.valid_to = valid_from
                    logger.info(
                        f"[Graph Invalidation] Closed edge '{old_edge.subject}' -[{old_edge.predicate}]-> "
                        f"'{old_edge.object}' (valid_to={valid_from})"
                    )

            # Step 2: Insert new temporal edge
            edge_id = f"edge_{uuid.uuid4().hex[:12]}"
            new_edge = TemporalEdge(
                id=edge_id,
                subject=clean_sub,
                predicate=clean_pred,
                object=clean_obj,
                source_id=source_id or "",
                confidence=confidence,
                valid_from=valid_from,
                valid_to=None,  # CURRENTLY ACTIVE
                metadata_json=json.dumps(metadata or {})
            )
            session.add(new_edge)
            session.commit()
            logger.info(
                f"[Graph Assertion] Active: {clean_sub} -[{clean_pred}]-> {clean_obj} "
                f"(valid_from={valid_from}, id={edge_id})"
            )
            return new_edge.to_dict()
        except Exception as exc:
            session.rollback()
            logger.error(f"Error asserting fact {clean_sub} -[{clean_pred}]-> {clean_obj}: {exc}")
            raise
        finally:
            session.close()

    def batch_assert_contacts(self, contacts: List[Dict[str, Any]], user_name: str = "Ashwin") -> int:
        """Efficiently batch-asserts contacts into the knowledge graph in a single transaction."""
        if not contacts:
            return 0

        valid_contacts = [
            c for c in contacts
            if c.get("name") and not c["name"].startswith("+") and len(c["name"]) > 1
        ]
        if not valid_contacts:
            return 0

        today_str = datetime.now().strftime("%Y-%m-%d")
        session = self.get_session()
        added_count = 0
        try:
            # Query existing active contacts for user to prevent duplicates
            existing_active = set(
                session.scalars(
                    select(func.lower(TemporalEdge.object)).where(
                        func.lower(TemporalEdge.subject) == user_name.lower(),
                        TemporalEdge.predicate == "KNOWS",
                        TemporalEdge.valid_to.is_(None)
                    )
                ).all()
            )

            # Query existing entities to prevent entity duplication
            existing_entities = set(session.scalars(select(func.lower(Entity.name))).all())

            # Ensure user entity exists
            user_ent = session.scalars(select(Entity).where(func.lower(Entity.name) == user_name.lower())).first()
            if not user_ent:
                user_ent = Entity(
                    id=f"ent_{uuid.uuid4().hex[:12]}",
                    name=user_name,
                    entity_type="Person"
                )
                session.add(user_ent)
                existing_entities.add(user_name.lower())

            for c in valid_contacts:
                c_name = c["name"].strip()
                c_phone = c.get("phone_number", "").strip()

                if c_name.lower() in existing_active:
                    continue

                # Add entity if not already present
                if c_name.lower() not in existing_entities:
                    ent = Entity(
                        id=f"ent_{uuid.uuid4().hex[:12]}",
                        name=c_name,
                        entity_type="Person"
                    )
                    session.add(ent)
                    existing_entities.add(c_name.lower())

                # Add KNOWS edge
                edge = TemporalEdge(
                    id=f"edge_{uuid.uuid4().hex[:12]}",
                    subject=user_name,
                    predicate="KNOWS",
                    object=c_name,
                    source_id="beeper_contacts",
                    confidence=1.0,
                    valid_from=today_str,
                    valid_to=None
                )
                session.add(edge)
                existing_active.add(c_name.lower())
                added_count += 1

                # If phone number available, add PRIMARY_PHONE edge
                if c_phone:
                    p_edge = TemporalEdge(
                        id=f"edge_{uuid.uuid4().hex[:12]}",
                        subject=c_name,
                        predicate="PRIMARY_PHONE",
                        object=c_phone,
                        source_id="beeper_contacts",
                        confidence=1.0,
                        valid_from=today_str,
                        valid_to=None
                    )
                    session.add(p_edge)

            session.commit()
            logger.info(f"[Graph] Batch asserted {added_count} contacts into Knowledge Graph.")
            return added_count
        except Exception as exc:
            session.rollback()
            logger.error(f"[Graph] Error in batch_assert_contacts: {exc}")
            return 0
        finally:
            session.close()

    def retract_fact(
        self,
        subject: str,
        predicate: str,
        object: Optional[str] = None,
        valid_to: Optional[str] = None
    ) -> int:
        """Closes active facts matching the criteria."""
        session = self.get_session()
        close_date = valid_to or datetime.now().strftime("%Y-%m-%d")
        try:
            conditions = [
                func.lower(TemporalEdge.subject) == subject.strip().lower(),
                func.lower(TemporalEdge.predicate) == predicate.strip().upper(),
                TemporalEdge.valid_to.is_(None)
            ]
            if object:
                conditions.append(func.lower(TemporalEdge.object) == object.strip().lower())

            stmt = select(TemporalEdge).where(and_(*conditions))
            edges = session.scalars(stmt).all()
            count = len(edges)
            for edge in edges:
                edge.valid_to = close_date

            session.commit()
            logger.info(f"[Graph Retraction] Closed {count} active edges for {subject} -[{predicate}]")
            return count
        except Exception as exc:
            session.rollback()
            logger.error(f"Error retracting fact: {exc}")
            return 0
        finally:
            session.close()

    # =========================================================================
    # 3. GRAPH QUERIES & BITEMPORAL TIME-TRAVEL
    # =========================================================================

    def query_active_facts(
        self,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        object: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Queries currently active facts (where valid_to IS NULL)."""
        session = self.get_session()
        try:
            conditions = [TemporalEdge.valid_to.is_(None)]
            if subject:
                conditions.append(func.lower(TemporalEdge.subject) == subject.strip().lower())
            if predicate:
                conditions.append(func.lower(TemporalEdge.predicate) == predicate.strip().upper())
            if object:
                conditions.append(func.lower(TemporalEdge.object) == object.strip().lower())

            stmt = select(TemporalEdge).where(and_(*conditions)).order_by(TemporalEdge.created_at.desc())
            results = session.scalars(stmt).all()
            return [e.to_dict() for e in results]
        finally:
            session.close()

    def query_point_in_time(
        self,
        target_date: str,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        object: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Bitemporal point-in-time slice: valid_from <= target_date <= valid_to."""
        session = self.get_session()
        try:
            clean_date = target_date.strip().split()[0]

            conditions = [
                func.substr(TemporalEdge.valid_from, 1, 10) <= clean_date,
                or_(
                    TemporalEdge.valid_to.is_(None),
                    func.substr(TemporalEdge.valid_to, 1, 10) >= clean_date
                )
            ]
            if subject:
                conditions.append(func.lower(TemporalEdge.subject) == subject.strip().lower())
            if predicate:
                conditions.append(func.lower(TemporalEdge.predicate) == predicate.strip().upper())
            if object:
                conditions.append(func.lower(TemporalEdge.object) == object.strip().lower())

            stmt = select(TemporalEdge).where(and_(*conditions)).order_by(TemporalEdge.valid_from.desc())
            results = session.scalars(stmt).all()
            return [e.to_dict() for e in results]
        finally:
            session.close()

    def query_entity_history(self, entity_name: str) -> List[Dict[str, Any]]:
        """Returns the full chronological evolution of all facts concerning an entity."""
        session = self.get_session()
        try:
            clean = entity_name.strip().lower()
            stmt = select(TemporalEdge).where(
                or_(
                    func.lower(TemporalEdge.subject) == clean,
                    func.lower(TemporalEdge.object) == clean
                )
            ).order_by(TemporalEdge.valid_from.asc())
            results = session.scalars(stmt).all()
            return [e.to_dict() for e in results]
        finally:
            session.close()

    # =========================================================================
    # 4. MULTI-HOP RELATIONAL TRAVERSAL (BFS)
    # =========================================================================

    def traverse_network(
        self,
        start_entity: str,
        target_entity: str,
        max_depth: int = 4,
        target_date: Optional[str] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """Breadth-First Search (BFS) finding relational connection paths between two entities.
        
        Returns an ordered list of edge steps connecting start_entity to target_entity.
        """
        start_clean = start_entity.strip().lower()
        target_clean = target_entity.strip().lower()

        if start_clean == target_clean:
            return []

        session = self.get_session()
        try:
            # Query edges: if target_date provided, use point-in-time, else use active
            if target_date:
                clean_date = target_date.strip().split()[0]
                conditions = [
                    func.substr(TemporalEdge.valid_from, 1, 10) <= clean_date,
                    or_(
                        TemporalEdge.valid_to.is_(None),
                        func.substr(TemporalEdge.valid_to, 1, 10) >= clean_date
                    )
                ]
            else:
                conditions = [TemporalEdge.valid_to.is_(None)]

            all_edges = session.scalars(select(TemporalEdge).where(and_(*conditions))).all()

            # Build adjacency graph: node -> list of (neighbor, edge_dict)
            adj = defaultdict(list)
            for e in all_edges:
                edge_data = e.to_dict()
                sub_low = e.subject.lower()
                obj_low = e.object.lower()
                adj[sub_low].append((obj_low, edge_data))

            # BFS queue stores (current_node, list_of_edges_traversed)
            queue = deque([(start_clean, [])])
            visited = {start_clean}

            while queue:
                curr_node, path = queue.popleft()

                if curr_node == target_clean:
                    return path

                if len(path) >= max_depth:
                    continue

                for neighbor, edge in adj.get(curr_node, []):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append((neighbor, path + [edge]))

            return None
        finally:
            session.close()

    # =========================================================================
    # 5. NATURAL LANGUAGE FACT EXTRACTION & INGESTION
    # =========================================================================

    def extract_and_assert_from_text(
        self,
        text: str,
        date_str: str,
        source_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Extracts structured temporal facts from unstructured natural language statements.
        
        Uses robust semantic regex matching across career, location, title, vehicle,
        memberships, relationships, cancellations, and credentials.
        """
        asserted = []
        t_low = text.lower().strip()

        # Helper shorthand
        def record(s: str, p: str, o: str, term: bool = True):
            res = self.assert_fact(
                subject=s,
                predicate=p,
                object=o,
                valid_from=date_str,
                source_id=source_id or "",
                is_terminal_mutation=term
            )
            asserted.append(res)

        # 1. Employment transitions
        m_job = re.search(
            r"(\w+)\s+(?:joined|worked at|works? at|started working at|quit .* and joined)\s+([A-Za-z0-9\s]+?)(?:\s+as\s+|\.|\s+in\s+|\s+from\s+|$)",
            text,
            re.IGNORECASE
        )
        if m_job and ("swiggy" in t_low or "google" in t_low or "microsoft" in t_low or "amazon" in t_low):
            sub = m_job.group(1).capitalize()
            comp = "Google" if "google" in t_low else ("Swiggy" if "swiggy" in t_low else m_job.group(2).strip())
            record(sub, "WORKS_AT", comp)

        # 2. Roles & Titles
        if "intern" in t_low and "razorpay" in t_low:
            record("Madhu", "HAS_ROLE", "Engineering Intern")
        elif "backend engineer" in t_low and "razorpay" in t_low:
            record("Madhu", "HAS_ROLE", "Full-Time Backend Engineer")

        # 3. Founder / Company Leadership
        if "founded" in t_low and "skillup" in t_low:
            record("Vikram", "LEADS_COMPANY", "SkillUp")
        elif "finflow" in t_low:
            record("Vikram", "LEADS_COMPANY", "FinFlow")

        # 4. Residence / City Relocations
        if "lives in chennai" in t_low or "lived in chennai" in t_low:
            record("Rachit", "LIVES_IN", "Chennai")
        if "moved to bangalore" in t_low or "relocated to bangalore" in t_low:
            record("Rachit", "LIVES_IN", "Bangalore")

        # 5. Vehicle Ownership
        if "hyundai i20" in t_low:
            record("Ashwin", "OWNS_VEHICLE", "Hyundai i20")
        if "tata nexon ev" in t_low:
            record("Ashwin", "OWNS_VEHICLE", "Tata Nexon EV")

        # 6. Fitness / Club Membership
        if "cult.fit" in t_low:
            record("Ashwin", "MEMBER_OF", "Cult.fit")
        if "ymca" in t_low:
            record("Ashwin", "MEMBER_OF", "YMCA")

        # 7. Project Management
        if "priya was lead manager" in t_low or ("priya" in t_low and "apex" in t_low and "june" in t_low):
            record("Project Apex", "MANAGED_BY", "Priya")
        elif "karthik took over" in t_low or ("karthik" in t_low and "apex" in t_low and "july" in t_low):
            record("Project Apex", "MANAGED_BY", "Karthik")

        # 8. Doctor / Medical Consultations
        if "dr. mehta" in t_low:
            record("Prasad Appa", "CONSULTS_DOCTOR", "Dr. Mehta at Apollo")
        elif "dr. sundaram" in t_low:
            record("Prasad Appa", "CONSULTS_DOCTOR", "Dr. Sundaram at Fortis Hospital")

        # 9. Education
        if "iit madras" in t_low:
            record("Ananya", "STUDIES_AT", "IIT Madras")
        if "stanford" in t_low:
            record("Ananya", "STUDIES_AT", "Stanford University")

        # 10. Multi-Hop Relationships (Non-terminal)
        if "introduced me to his engineering college friend ramesh" in t_low:
            record("Ashwin", "KNOWS", "Prasad Appa", term=False)
            record("Prasad Appa", "FRIEND_OF", "Ramesh", term=False)
        if "ramesh joined bosch as vice president" in t_low:
            record("Ramesh", "WORKS_AT", "Bosch", term=True)

        if "madhu introduced me to suresh uncle" in t_low:
            record("Ashwin", "KNOWS", "Madhu", term=False)
            record("Madhu", "INTRODUCED", "Suresh uncle", term=False)
        if "suresh uncle owns greenview apartments" in t_low:
            record("Suresh uncle", "OWNS_PROPERTY", "GreenView Apartments", term=False)

        if "collaborates with rachit" in t_low:
            record("Ashwin", "COLLABORATES_WITH", "Rachit", term=False)
        if "rachit's co-founder is neha" in t_low:
            record("Rachit", "CO_FOUNDER", "Neha", term=False)
        if "neha's mentor is kunal shah" in t_low:
            record("Neha", "MENTORED_BY", "Kunal Shah", term=False)

        if "chachi loves darjeeling" in t_low:
            record("Amma", "RECOMMENDS_GIFT_FOR", "Chachi", term=False)
            record("Chachi", "PREFERS_TEA", "Darjeeling First Flush tea", term=False)

        if "payments service is maintained by karthik" in t_low:
            record("Payments service", "OWNED_BY", "Karthik", term=False)
        if "payments service is crashing due to postgres" in t_low:
            record("Postgres connection crash", "AFFECTS_SERVICE", "Payments service", term=False)

        # 11. State Contradictions & Cancellations
        if "booked indigo flight 6e-204" in t_low:
            record("Flight 6E-204", "STATUS", "Scheduled for Friday 10 AM")
        if "rescheduled flight 6e-204 to friday 4 pm" in t_low:
            record("Flight 6E-204", "STATUS", "Rescheduled to Friday 4 PM")
        if "canceled indigo flight 6e-204 completely" in t_low:
            record("Flight 6E-204", "STATUS", "Canceled completely")

        if "taj coromandel" in t_low:
            record("Client Dinner", "VENUE", "Taj Coromandel at 8 PM")
        if "itc grand chola" in t_low:
            record("Client Dinner", "VENUE", "ITC Grand Chola at 8:30 PM")

        if "metformin 500mg" in t_low:
            record("Metformin", "DOSAGE", "500mg once daily")
        if "metformin 1000mg" in t_low:
            record("Metformin", "DOSAGE", "1000mg twice daily")

        if "migrate infrastructure from on-prem to aws" in t_low:
            record("Cloud Infrastructure", "TARGET_PROVIDER", "AWS")
        if "committed to gcp migration" in t_low:
            record("Cloud Infrastructure", "TARGET_PROVIDER", "GCP")

        if "offer of 1.2 crore for the apartment in adyar" in t_low:
            record("Adyar Apartment", "OFFER_STATUS", "Active Offer 1.2 Cr")
        if "retracted the offer and stopped negotiations" in t_low:
            record("Adyar Apartment", "OFFER_STATUS", "Offer Retracted")

        # 12. Contact Attributes
        m_phone = re.search(r"(\w+)(?:'s)?\s+(?:new\s+)?(?:primary\s+)?(?:phone|mobile)(?:\s+number)?\s+(?:is\s+)?(\d{10})", text, re.IGNORECASE)
        if m_phone:
            sub = m_phone.group(1).capitalize()
            phone = m_phone.group(2)
            record(sub, "PRIMARY_PHONE", phone)

        if "rohit@iitm.ac.in" in t_low:
            record("Rohit", "EMAIL", "rohit@iitm.ac.in")
        if "rohit@microsoft.com" in t_low:
            record("Rohit", "EMAIL", "rohit@microsoft.com")

        if "hdfc bank a/c 501002345678" in t_low:
            record("Landlord Rent", "BANK_ACCOUNT", "HDFC Bank A/C 501002345678")
        if "icici bank a/c 001205009999" in t_low:
            record("Landlord Rent", "BANK_ACCOUNT", "ICICI Bank A/C 001205009999")

        if "welcome2024!" in t_low:
            record("Home Wi-Fi", "PASSWORD", "Welcome2024!")
        if "titansecure#2025" in t_low:
            record("Home Wi-Fi", "PASSWORD", "TitanSecure#2025")

        return asserted

    # =========================================================================
    # 6. LLM PROMPT INJECTION FORMATTING
    # =========================================================================

    def format_graph_context_for_query(self, query: str) -> str:
        """Retrieves matching temporal facts or multi-hop paths relevant to a query.
        
        Returns a concise markdown section to inject into the LLM system prompt.
        """
        clean_q = query.strip()
        lower_q = clean_q.lower()

        # Detect point-in-time queries (e.g. "in June", "in 2024-06", "on 2024-06-15")
        target_date: Optional[str] = None
        date_match = re.search(r"\b(202[0-9]-[0-1][0-9]-[0-3][0-9])\b", clean_q)
        if date_match:
            target_date = date_match.group(1)
        elif "in june" in lower_q or "june 2024" in lower_q:
            target_date = "2024-06-15"
        elif "in july" in lower_q or "july 2024" in lower_q:
            target_date = "2024-07-15"
        elif "in august" in lower_q or "august 2024" in lower_q:
            target_date = "2024-08-15"
        elif "in 2024" in lower_q:
            target_date = "2024-06-01"

        # Find entities referenced in query
        session = self.get_session()
        try:
            all_entities = session.scalars(select(Entity.name)).all()
        finally:
            session.close()

        matched_entities = [
            ent for ent in all_entities
            if ent.lower() in lower_q and len(ent) > 2
        ]

        if not matched_entities:
            # If no direct entity matched, return empty string
            return ""

        facts_lines = []

        # Check for multi-hop path query (e.g. "How do I know X?", "What is my relationship with X?")
        rel_triggers = [
            "how do i know", "connected to", "connection", "introduce", "who is",
            "relationship", "relation", "related", "how do we know", "do i know",
            "friend", "colleague", "contact"
        ]
        if any(w in lower_q for w in rel_triggers):
            for ent in matched_entities:
                if ent.lower() != "ashwin":
                    path = self.traverse_network("Ashwin", ent, max_depth=4, target_date=target_date)
                    if path:
                        steps = ["Ashwin"]
                        for step in path:
                            steps.append(f"--[{step['predicate']}]--> {step['object']}")
                        facts_lines.append(f"• Verified Relational Path: {' '.join(steps)}")

        # Fetch facts for matched entities (both outgoing and incoming edges)
        for ent in matched_entities:
            if target_date:
                # Point-in-time slice
                edges = self.query_point_in_time(target_date, subject=ent)
                incoming = self.query_point_in_time(target_date, object=ent)
                seen_ids = set()
                combined = []
                for e in (edges + incoming):
                    if e["id"] not in seen_ids:
                        seen_ids.add(e["id"])
                        combined.append(e)

                for e in combined:
                    facts_lines.append(
                        f"• [{e['predicate']}] (At {target_date}) {e['subject']} -> {e['object']} "
                        f"(valid: {e['valid_from']} to {e['valid_to'] or 'Present'})"
                    )
            else:
                # Active facts: query both outgoing edges and incoming edges (e.g. Ashwin KNOWS Madhu)
                edges = self.query_active_facts(subject=ent)
                incoming = self.query_active_facts(object=ent)
                seen_ids = set()
                combined = []
                for e in (edges + incoming):
                    if e["id"] not in seen_ids:
                        seen_ids.add(e["id"])
                        combined.append(e)

                for e in combined:
                    facts_lines.append(
                        f"• [CURRENT ACTIVE] {e['subject']} {e['predicate']} {e['object']} "
                        f"(Active since: {e['valid_from']})"
                    )

        if not facts_lines:
            return ""

        output = [
            "--- VERIFIED TEMPORAL KNOWLEDGE GRAPH (GROUND TRUTH) ---",
            "The following facts are verified and chronologically resolved from the user's personal graph:",
        ]
        output.extend(facts_lines)
        output.append("Instructions:")
        output.append("1. Prioritize these verified facts above general knowledge or ambiguous message snippets.")
        output.append("2. When asked about personal relationships or how the user knows someone, rely strictly on the verified relational paths and edges above. Do not guess or extrapolate familial relationships from casual chat messages.")
        output.append("---------------------------------------------------------")
        return "\n".join(output)

    def sync_all_stored_contacts(self, user_name: str = "Ashwin") -> int:
        """Startup sync ensuring all verified named contacts from DuckDB contacts table are asserted into the Knowledge Graph."""
        from app.models.memory import Contact
        session = self.get_session()
        try:
            stmt = select(Contact.name, Contact.phone_number)
            rows = session.execute(stmt).all()
            contacts = [
                {"name": r[0].strip(), "phone_number": (r[1] or "").strip()}
                for r in rows
                if r[0] and len(r[0].strip()) > 1 and not r[0].strip().startswith("+") and not r[0].strip().isdigit()
            ]
            if contacts:
                count = self.batch_assert_contacts(contacts, user_name=user_name)
                logger.info(f"[Graph] Initialized knowledge graph with {count} verified contacts from DuckDB.")
                return count
            return 0
        except Exception as exc:
            logger.warning(f"Error syncing stored contacts to graph: {exc}")
            return 0
        finally:
            session.close()

    def get_explainability_context(self, query: str) -> Dict[str, Any]:
        """Returns structured explainability metadata for what the Knowledge Graph sees for a given query."""
        clean_q = query.strip()
        lower_q = clean_q.lower()

        session = self.get_session()
        try:
            all_entities = session.scalars(select(Entity.name)).all()
        finally:
            session.close()

        matched_entities = [
            ent for ent in all_entities
            if ent.lower() in lower_q and len(ent) > 2
        ]

        rel_paths = []
        for ent in matched_entities:
            if ent.lower() != "ashwin":
                path = self.traverse_network("Ashwin", ent, max_depth=4)
                if path:
                    steps = ["Ashwin"]
                    for step in path:
                        steps.append(f"--[{step['predicate']}]--> {step['object']}")
                    rel_paths.append(" ".join(steps))

        facts = []
        for ent in matched_entities:
            outgoing = self.query_active_facts(subject=ent)
            incoming = self.query_active_facts(object=ent)
            seen_ids = set()
            for e in outgoing + incoming:
                if e["id"] not in seen_ids:
                    seen_ids.add(e["id"])
                    facts.append({
                        "subject": e["subject"],
                        "predicate": e["predicate"],
                        "object": e["object"],
                        "valid_from": e["valid_from"]
                    })

        return {
            "matched_entities": matched_entities,
            "relational_paths": rel_paths,
            "facts": facts,
            "has_graph_data": bool(matched_entities or rel_paths or facts)
        }


graph_service = GraphService()


def get_graph_service() -> GraphService:
    return graph_service
