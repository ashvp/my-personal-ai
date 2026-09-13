"""105 Comprehensive Test Cases & Evaluation Benchmark Dataset.

Covers 7 distinct functional & cognitive dimensions:
1. Message Intent & First-Person Sanitization (25 cases)
2. Cellular Calling & Phone Sanitization (20 cases)
3. Relationship & Contact Alias Resolution (15 cases)
4. Follow-Up Intent & Pronoun Continuity (10 cases)
5. Action Intent Classification (15 cases)
6. DuckDB 3-Tier Cognitive Memory Engine (10 cases)
7. Temporal Knowledge Graph Benchmark Scenarios (10 cases)
"""

DATASET_105_CASES = {
    # =========================================================================
    # 1. MESSAGE INTENT & FIRST-PERSON SANITIZATION (25 CASES)
    # =========================================================================
    "message_sanitization": [
        {
            "id": "MSG_01",
            "input": "tell amma that im going to ymca today",
            "expected_message": "I'm going to YMCA today.",
            "forbidden_prefixes": ["tell amma that", "please tell", "tell", "telling"],
            "must_start_with": "I'm"
        },
        {
            "id": "MSG_02",
            "input": "tell dad ill be 10 mins late",
            "expected_message": "I'll be 10 mins late.",
            "forbidden_prefixes": ["tell dad that", "tell dad", "please tell"],
            "must_start_with": "I'll"
        },
        {
            "id": "MSG_03",
            "input": "ask prasad to buy pizza and come home",
            "expected_message": "Please buy pizza and come home.",
            "forbidden_prefixes": ["ask prasad to", "tell prasad to", "ask him to"],
            "must_start_with": "Please"
        },
        {
            "id": "MSG_04",
            "input": "tell mom not to wait for dinner",
            "expected_message": "Please do not wait for dinner.",
            "forbidden_prefixes": ["tell mom", "tell her"],
            "must_start_with": "Please do not"
        },
        {
            "id": "MSG_05",
            "input": "text appa telling him to come early",
            "expected_message": "Please come early.",
            "forbidden_prefixes": ["text appa", "telling him to"],
            "must_start_with": "Please"
        },
        {
            "id": "MSG_06",
            "input": "inform boss that presentation is ready",
            "expected_message": "Presentation is ready.",
            "forbidden_prefixes": ["inform boss that", "inform"],
            "must_start_with": "Presentation"
        },
        {
            "id": "MSG_07",
            "input": "ping rahul say reach home safe",
            "expected_message": "Please reach home safe.",
            "forbidden_prefixes": ["ping rahul", "say"],
            "must_start_with": "Please"
        },
        {
            "id": "MSG_08",
            "input": "tell madhu saying got the offer letter",
            "expected_message": "I got the offer letter.",
            "forbidden_prefixes": ["tell madhu", "saying"],
            "must_contain": "offer letter"
        },
        {
            "id": "MSG_09",
            "input": "ask dad if he took his medicines",
            "expected_message": "Did you take your medicines?",
            "forbidden_prefixes": ["ask dad if", "if he"],
            "must_start_with": "Did you"
        },
        {
            "id": "MSG_10",
            "input": "tell rachit that we are meeting at 6pm",
            "expected_message": "We are meeting at 6pm.",
            "forbidden_prefixes": ["tell rachit that", "tell"],
            "must_start_with": "We"
        },
        {
            "id": "MSG_11",
            "input": "remind brother to bring his laptop charger",
            "expected_message": "Please bring your laptop charger.",
            "forbidden_prefixes": ["remind brother to", "his"],
            "must_contain": "your laptop charger"
        },
        {
            "id": "MSG_12",
            "input": "tell suresh i have reached the airport",
            "expected_message": "I have reached the airport.",
            "forbidden_prefixes": ["tell suresh"],
            "must_start_with": "I"
        },
        {
            "id": "MSG_13",
            "input": "message priya saying ill call in 15 mins",
            "expected_message": "I'll call in 15 mins.",
            "forbidden_prefixes": ["message priya", "saying"],
            "must_start_with": "I'll"
        },
        {
            "id": "MSG_14",
            "input": "tell mom don't cook dinner for me",
            "expected_message": "Please do not cook dinner for me.",
            "forbidden_prefixes": ["tell mom", "don't cook"],
            "must_start_with": "Please do not"
        },
        {
            "id": "MSG_15",
            "input": "ask arun whether he can share the notes",
            "expected_message": "Can you share the notes?",
            "forbidden_prefixes": ["ask arun whether", "he can"],
            "must_contain": "share the notes"
        },
        {
            "id": "MSG_16",
            "input": "tell grandma that we reached safely",
            "expected_message": "We reached safely.",
            "forbidden_prefixes": ["tell grandma that"],
            "must_start_with": "We"
        },
        {
            "id": "MSG_17",
            "input": "text vishnu to send the github repo link",
            "expected_message": "Please send the github repo link.",
            "forbidden_prefixes": ["text vishnu to"],
            "must_start_with": "Please"
        },
        {
            "id": "MSG_18",
            "input": "tell him to pick up milk on his way home",
            "expected_message": "Please pick up milk on your way home.",
            "forbidden_prefixes": ["tell him to", "his way"],
            "must_contain": "your way home"
        },
        {
            "id": "MSG_19",
            "input": "inform the team that server deploy succeeded",
            "expected_message": "Server deploy succeeded.",
            "forbidden_prefixes": ["inform the team that"],
            "must_contain": "Server deploy succeeded"
        },
        {
            "id": "MSG_20",
            "input": "tell kartik im outside his house",
            "expected_message": "I'm outside your house.",
            "forbidden_prefixes": ["tell kartik", "his house"],
            "must_contain": "your house"
        },
        {
            "id": "MSG_21",
            "input": "ask rohit if he has reached delhi",
            "expected_message": "Have you reached delhi?",
            "forbidden_prefixes": ["ask rohit if"],
            "must_start_with": "Have you"
        },
        {
            "id": "MSG_22",
            "input": "tell uncle i received the parcel thank you",
            "expected_message": "I received the parcel thank you.",
            "forbidden_prefixes": ["tell uncle"],
            "must_start_with": "I"
        },
        {
            "id": "MSG_23",
            "input": "text deepak please pay the electricity bill",
            "expected_message": "Please pay the electricity bill.",
            "forbidden_prefixes": ["text deepak"],
            "must_start_with": "Please"
        },
        {
            "id": "MSG_24",
            "input": "tell ananya that project deadline is extended",
            "expected_message": "Project deadline is extended.",
            "forbidden_prefixes": ["tell ananya that"],
            "must_contain": "Project deadline is extended"
        },
        {
            "id": "MSG_25",
            "input": "tell karthik ive sent the email",
            "expected_message": "I've sent the email.",
            "forbidden_prefixes": ["tell karthik"],
            "must_start_with": "I've"
        }
    ],

    # =========================================================================
    # 2. CELLULAR CALLING & PHONE SANITIZATION (20 CASES)
    # =========================================================================
    "phone_sanitization": [
        {"id": "PHN_01", "raw": "+919940020084", "expected_dialer": "9940020084", "expected_wa": "919940020084"},
        {"id": "PHN_02", "raw": "919940020084", "expected_dialer": "9940020084", "expected_wa": "919940020084"},
        {"id": "PHN_03", "raw": "09940020084", "expected_dialer": "9940020084", "expected_wa": "919940020084"},
        {"id": "PHN_04", "raw": "9940020084", "expected_dialer": "9940020084", "expected_wa": "919940020084"},
        {"id": "PHN_05", "raw": "+91 99400 20084", "expected_dialer": "9940020084", "expected_wa": "919940020084"},
        {"id": "PHN_06", "raw": "+91-98401-12345", "expected_dialer": "9840112345", "expected_wa": "919840112345"},
        {"id": "PHN_07", "raw": "09840112345", "expected_dialer": "9840112345", "expected_wa": "919840112345"},
        {"id": "PHN_08", "raw": "9840112345", "expected_dialer": "9840112345", "expected_wa": "919840112345"},
        {"id": "PHN_09", "raw": "+1 (415) 555-2671", "expected_dialer": "+14155552671", "expected_wa": "14155552671"},
        {"id": "PHN_10", "raw": "+44 7911 123456", "expected_dialer": "+447911123456", "expected_wa": "447911123456"},
        {"id": "PHN_11", "raw": "99400-20084", "expected_dialer": "9940020084", "expected_wa": "919940020084"},
        {"id": "PHN_12", "raw": "(99400) 20084", "expected_dialer": "9940020084", "expected_wa": "919940020084"},
        {"id": "PHN_13", "raw": "+91 98840 98840", "expected_dialer": "9884098840", "expected_wa": "919884098840"},
        {"id": "PHN_14", "raw": "09884098840", "expected_dialer": "9884098840", "expected_wa": "919884098840"},
        {"id": "PHN_15", "raw": "9884098840", "expected_dialer": "9884098840", "expected_wa": "919884098840"},
        {"id": "PHN_16", "raw": "+919710012345", "expected_dialer": "9710012345", "expected_wa": "919710012345"},
        {"id": "PHN_17", "raw": "09710012345", "expected_dialer": "9710012345", "expected_wa": "919710012345"},
        {"id": "PHN_18", "raw": "+65 9123 4567", "expected_dialer": "+6591234567", "expected_wa": "6591234567"},
        {"id": "PHN_19", "raw": "+91 80560 11223", "expected_dialer": "8056011223", "expected_wa": "918056011223"},
        {"id": "PHN_20", "raw": "918056011223", "expected_dialer": "8056011223", "expected_wa": "918056011223"}
    ],

    # =========================================================================
    # 3. RELATIONSHIP & CONTACT ALIAS RESOLUTION (15 CASES)
    # =========================================================================
    "contact_aliases": [
        {"id": "ALIAS_01", "query": "appa", "expected_match": "Prasad Appa", "relation": "father"},
        {"id": "ALIAS_02", "query": "dad", "expected_match": "Prasad Appa", "relation": "father"},
        {"id": "ALIAS_03", "query": "father", "expected_match": "Prasad Appa", "relation": "father"},
        {"id": "ALIAS_04", "query": "papa", "expected_match": "Prasad Appa", "relation": "father"},
        {"id": "ALIAS_05", "query": "call appa", "expected_match": "Prasad Appa", "relation": "father"},
        {"id": "ALIAS_06", "query": "dial dad", "expected_match": "Prasad Appa", "relation": "father"},
        {"id": "ALIAS_07", "query": "ring to father", "expected_match": "Prasad Appa", "relation": "father"},
        {"id": "ALIAS_08", "query": "amma", "expected_match": "Amma", "relation": "mother"},
        {"id": "ALIAS_09", "query": "mom", "expected_match": "Amma", "relation": "mother"},
        {"id": "ALIAS_10", "query": "mother", "expected_match": "Amma", "relation": "mother"},
        {"id": "ALIAS_11", "query": "maa", "expected_match": "Amma", "relation": "mother"},
        {"id": "ALIAS_12", "query": "call to amma", "expected_match": "Amma", "relation": "mother"},
        {"id": "ALIAS_13", "query": "Prasad", "expected_match": "Prasad Appa", "relation": "direct_name"},
        {"id": "ALIAS_14", "query": "Madhu", "expected_match": "Madhu", "relation": "direct_name"},
        {"id": "ALIAS_15", "query": "Rachit", "expected_match": "Rachit", "relation": "direct_name"}
    ],

    # =========================================================================
    # 4. FOLLOW-UP INTENT & PRONOUN CONTINUITY (10 CASES)
    # =========================================================================
    "followup_continuity": [
        {
            "id": "FOL_01",
            "prompt": "send that to him in whatsapp",
            "history": [
                {"role": "user", "content": "Draft a quick message to Prasad Appa regarding meeting at 6pm"},
                {"role": "assistant", "content": "Here is the drafted message:\n\"Hi Prasad, let's meet at 6pm today.\""}
            ],
            "expected_recip": "Prasad Appa",
            "expected_msg": "Hi Prasad, let's meet at 6pm today."
        },
        {
            "id": "FOL_02",
            "prompt": "send it to madhu via whatsapp",
            "history": [
                {"role": "user", "content": "Draft an update saying code review is done"},
                {"role": "assistant", "content": "\"Code review is completed and merged.\""}
            ],
            "expected_recip": "madhu",
            "expected_msg": "Code review is completed and merged."
        },
        {
            "id": "FOL_03",
            "prompt": "forward that to him",
            "history": [
                {"role": "user", "content": "Tell Appa that I am leaving now"},
                {"role": "assistant", "content": "\"I am leaving now.\""}
            ],
            "expected_recip": "Appa",
            "expected_msg": "I am leaving now."
        },
        {
            "id": "FOL_04",
            "prompt": "send this message to Rachit",
            "history": [
                {"role": "user", "content": "What should I say about the server migration?"},
                {"role": "assistant", "content": "\"The server migration is scheduled for tonight at 10 PM.\""}
            ],
            "expected_recip": "Rachit",
            "expected_msg": "The server migration is scheduled for tonight at 10 PM."
        },
        {
            "id": "FOL_05",
            "prompt": "yes send it",
            "history": [
                {"role": "user", "content": "Can you prepare a message for Amma?"},
                {"role": "assistant", "content": "I prepared this for Amma:\n\"I will reach home by 7 PM.\""}
            ],
            "expected_recip": "Amma",
            "expected_msg": "I will reach home by 7 PM."
        },
        {
            "id": "FOL_06",
            "prompt": "send that to her in whatsapp",
            "history": [
                {"role": "user", "content": "Draft a thank you message for Amma for lunch"},
                {"role": "assistant", "content": "\"Thank you for the delicious lunch today!\""}
            ],
            "expected_recip": "Amma",
            "expected_msg": "Thank you for the delicious lunch today!"
        },
        {
            "id": "FOL_07",
            "prompt": "forward it to Prasad",
            "history": [
                {"role": "user", "content": "Draft note about airport pickup"},
                {"role": "assistant", "content": "\"Flight has landed, heading to arrival gate B.\""}
            ],
            "expected_recip": "Prasad",
            "expected_msg": "Flight has landed, heading to arrival gate B."
        },
        {
            "id": "FOL_08",
            "prompt": "send this in whatsapp",
            "history": [
                {"role": "user", "content": "Draft a message for Dad"},
                {"role": "assistant", "content": "\"I have transferred the money to your account.\""}
            ],
            "expected_recip": "Dad",
            "expected_msg": "I have transferred the money to your account."
        },
        {
            "id": "FOL_09",
            "prompt": "ok send that",
            "history": [
                {"role": "user", "content": "Tell Madhu that I have updated the branch"},
                {"role": "assistant", "content": "\"I have updated the feature branch with your requested changes.\""}
            ],
            "expected_recip": "Madhu",
            "expected_msg": "I have updated the feature branch with your requested changes."
        },
        {
            "id": "FOL_10",
            "prompt": "send that to them via whatsapp",
            "history": [
                {"role": "user", "content": "Draft notification for Prasad Appa"},
                {"role": "assistant", "content": "\"The doctor appointment is confirmed for tomorrow 10 AM.\""}
            ],
            "expected_recip": "Prasad Appa",
            "expected_msg": "The doctor appointment is confirmed for tomorrow 10 AM."
        }
    ],

    # =========================================================================
    # 5. ACTION INTENT CLASSIFICATION (15 CASES)
    # =========================================================================
    "intent_routing": [
        {"id": "INT_01", "prompt": "tell amma that im going to gym", "expected_action": "whatsapp", "expected_intent": "SEND_WHATSAPP"},
        {"id": "INT_02", "prompt": "call appa right now", "expected_action": "call", "expected_intent": "CALL_CONTACT"},
        {"id": "INT_03", "prompt": "dial 9940020084", "expected_action": "call", "expected_intent": "CALL_CONTACT"},
        {"id": "INT_04", "prompt": "what is on my plate today?", "expected_action": "daily_briefing", "expected_intent": "DAILY_BRIEFING"},
        {"id": "INT_05", "prompt": "give me my morning executive briefing", "expected_action": "daily_briefing", "expected_intent": "DAILY_BRIEFING"},
        {"id": "INT_06", "prompt": "did anyone text me on whatsapp about dinner?", "expected_action": "message_lookup", "expected_intent": "MESSAGE_LOOKUP"},
        {"id": "INT_07", "prompt": "what was my last message from madhu?", "expected_action": "message_lookup", "expected_intent": "MESSAGE_LOOKUP"},
        {"id": "INT_08", "prompt": "what was my last email?", "expected_action": "email_lookup", "expected_intent": "EMAIL_LOOKUP"},
        {"id": "INT_09", "prompt": "check my emails from google", "expected_action": "email_lookup", "expected_intent": "EMAIL_LOOKUP"},
        {"id": "INT_10", "prompt": "how do black holes form in astronomy?", "expected_action": "chat", "expected_intent": "FAST_CHAT"},
        {"id": "INT_11", "prompt": "write a python function to invert a binary tree", "expected_action": "chat", "expected_intent": "FAST_CHAT"},
        {"id": "INT_12", "prompt": "Analyze the time complexity and memory trade-offs of A* vs Dijkstra algorithm", "expected_action": "chat", "expected_intent": "DEEP_REASON"},
        {"id": "INT_13", "prompt": "ring Prasad on phone", "expected_action": "call", "expected_intent": "CALL_CONTACT"},
        {"id": "INT_14", "prompt": "ask madhu to review pull request 42", "expected_action": "whatsapp", "expected_intent": "SEND_WHATSAPP"},
        {"id": "INT_15", "prompt": "what unread emails do i have from university?", "expected_action": "email_lookup", "expected_intent": "EMAIL_LOOKUP"}
    ],

    # =========================================================================
    # 6. DUCKDB 3-TIER COGNITIVE MEMORY ENGINE (10 CASES)
    # =========================================================================
    "memory_engine": [
        {"id": "MEM_01", "name": "Store & Retrieve Single Email", "type": "email_crud"},
        {"id": "MEM_02", "name": "Duplicate Email Upsert Idempotency", "type": "email_idempotency"},
        {"id": "MEM_03", "name": "Batch Upsert Messages with Memory Tiers", "type": "message_batch"},
        {"id": "MEM_04", "name": "Working Memory Query (<48 hours)", "type": "working_memory_query"},
        {"id": "MEM_05", "name": "Episodic Chronological Narrative Reconstruction", "type": "episodic_narrative"},
        {"id": "MEM_06", "name": "Latest Message Timestamp Extraction", "type": "latest_timestamp"},
        {"id": "MEM_07", "name": "Cognitive Memory Tier Aging (Working -> Episodic -> Archive)", "type": "tier_aging"},
        {"id": "MEM_08", "name": "Batch Contact Upsert & Indexing", "type": "contact_batch"},
        {"id": "MEM_09", "name": "Contact Substring & Case-Insensitive Search", "type": "contact_search"},
        {"id": "MEM_10", "name": "Intermediate Memory Digest Item Updates", "type": "intermediate_digest"}
    ],

    # =========================================================================
    # 7. TEMPORAL KNOWLEDGE GRAPH BENCHMARK SCENARIOS (10 CASES)
    # =========================================================================
    "temporal_kg_benchmarks": [
        {
            "id": "TKG_01",
            "type": "temporal_invalidation",
            "description": "Rahul job change: Motorq (2024) -> Google (2026)",
            "query": "Where does Rahul work right now?",
            "expected_active_entity": "Google",
            "superseded_entity": "Motorq"
        },
        {
            "id": "TKG_02",
            "type": "point_in_time_slice",
            "description": "Historical employment lookup at specific past timestamp",
            "query": "Where was Rahul working in July 2024?",
            "target_time": "2024-07-01",
            "expected_entity": "Motorq"
        },
        {
            "id": "TKG_03",
            "type": "multi_hop_traversal",
            "description": "2-hop link: Prasad introduced Rajesh -> Rajesh founded CloudScale",
            "query": "Which company was founded by the person Prasad introduced me to?",
            "expected_entity": "CloudScale",
            "hops": 2
        },
        {
            "id": "TKG_04",
            "type": "belief_trajectory",
            "description": "BMW purchase interest: considered -> rejected -> reconsidered",
            "query": "Am I still interested in getting a BMW?",
            "expected_trajectory": ["considered", "rejected", "reconsidered"],
            "final_state": "reconsidered"
        },
        {
            "id": "TKG_05",
            "type": "temporal_location_drift",
            "description": "City relocation: Priya lived in Bangalore (2023-2025), moved to London (2025)",
            "query": "Where does Priya currently live?",
            "expected_active_entity": "London",
            "superseded_entity": "Bangalore"
        },
        {
            "id": "TKG_06",
            "type": "provenance_evidence",
            "description": "Verifying edge carries non-empty ground truth message/source ID",
            "query": "Why do you believe Rahul works at Google?",
            "expected_evidence_required": True
        },
        {
            "id": "TKG_07",
            "type": "confidence_threshold_filter",
            "description": "Filtering low-confidence rumor edges (<0.6) from active facts",
            "query": "Who is Ashwin's manager?",
            "min_confidence": 0.75
        },
        {
            "id": "TKG_08",
            "type": "transitive_relationship",
            "description": "Project ownership: Ashwin owns LocalAI -> LocalAI uses DuckDB",
            "query": "What database is used by the project Ashwin is building?",
            "expected_entity": "DuckDB"
        },
        {
            "id": "TKG_09",
            "type": "temporal_preference_expiry",
            "description": "Temporary preference expiry: 'I'm vegetarian for Navratri this week'",
            "query": "Is Ashwin vegetarian next month?",
            "expected_result": "No / expired"
        },
        {
            "id": "TKG_10",
            "type": "reciprocal_entity_link",
            "description": "Bidirectional social edge: Ashwin <-> Prasad (family)",
            "query": "What is the relationship between Ashwin and Prasad Appa?",
            "expected_relation": "family / father"
        }
    ]
}
