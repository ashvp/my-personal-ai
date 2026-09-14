"""25 Head-to-Head Benchmark Scenarios: v1 (Unstructured RAG) vs. v2 (Temporal Knowledge Graph).

Evaluates the 5 canonical failure modes of unstructured vector search:
1. Temporal Fact Invalidation (Career, Role, and Location Drift)
2. Point-in-Time Historical Querying
3. Multi-Hop Relational Traversal (The Referral / Network Problem)
4. State Contradiction & Cancellation De-confliction
5. Contact Attribute Mutation (Phone & Email updates)
"""

V1_VS_V2_BENCHMARKS = [
    # =========================================================================
    # 1. TEMPORAL FACT INVALIDATION (CAREER & ROLE DRIFT) - 6 CASES
    # =========================================================================
    {
        "id": "TKG_01",
        "category": "fact_invalidation",
        "description": "Employment transition across 12 months",
        "events": [
            {"date": "2024-01-15", "text": "Rahul joined Swiggy as an SDE-2 in Bangalore."},
            {"date": "2025-01-20", "text": "Rahul quit Swiggy and joined Google as a Software Engineer."}
        ],
        "query": "Where does Rahul currently work?",
        "v1_expected_failure": "Rahul works at Swiggy and Google (or Swiggy due to vector similarity collision)",
        "v2_expected_ground_truth": "Google",
        "obsolete_entities": ["Swiggy"],
        "active_entities": ["Google"]
    },
    {
        "id": "TKG_02",
        "category": "fact_invalidation",
        "description": "Promotion / title change in the same company",
        "events": [
            {"date": "2023-08-01", "text": "Madhu is working as an Engineering Intern at Razorpay."},
            {"date": "2024-06-01", "text": "Madhu graduated and was promoted to Full-Time Backend Engineer at Razorpay."}
        ],
        "query": "What is Madhu's current job title?",
        "v1_expected_failure": "Engineering Intern and Backend Engineer",
        "v2_expected_ground_truth": "Full-Time Backend Engineer",
        "obsolete_entities": ["Engineering Intern", "Intern"],
        "active_entities": ["Full-Time Backend Engineer", "Backend Engineer"]
    },
    {
        "id": "TKG_03",
        "category": "fact_invalidation",
        "description": "Founder / Startup pivot",
        "events": [
            {"date": "2023-03-10", "text": "Vikram founded EdTech startup SkillUp."},
            {"date": "2024-11-05", "text": "SkillUp shut down. Vikram is now co-founder and CTO at FinFlow."}
        ],
        "query": "What company is Vikram leading right now?",
        "v1_expected_failure": "SkillUp and FinFlow",
        "v2_expected_ground_truth": "FinFlow",
        "obsolete_entities": ["SkillUp"],
        "active_entities": ["FinFlow"]
    },
    {
        "id": "TKG_04",
        "category": "fact_invalidation",
        "description": "City relocation",
        "events": [
            {"date": "2023-05-12", "text": "Rachit bought a flat and lives in Chennai."},
            {"date": "2025-02-01", "text": "Rachit moved to Bangalore for his new job at Zepto."}
        ],
        "query": "Where does Rachit currently reside?",
        "v1_expected_failure": "Chennai and Bangalore",
        "v2_expected_ground_truth": "Bangalore",
        "obsolete_entities": ["Chennai"],
        "active_entities": ["Bangalore"]
    },
    {
        "id": "TKG_05",
        "category": "fact_invalidation",
        "description": "Car ownership change",
        "events": [
            {"date": "2022-09-01", "text": "Ashwin bought a Hyundai i20."},
            {"date": "2025-04-10", "text": "Ashwin sold his Hyundai i20 and bought a Tata Nexon EV."}
        ],
        "query": "What car does Ashwin currently drive?",
        "v1_expected_failure": "Hyundai i20 and Tata Nexon EV",
        "v2_expected_ground_truth": "Tata Nexon EV",
        "obsolete_entities": ["Hyundai i20", "i20"],
        "active_entities": ["Tata Nexon EV", "Nexon EV"]
    },
    {
        "id": "TKG_06",
        "category": "fact_invalidation",
        "description": "Gym / Club membership",
        "events": [
            {"date": "2024-02-10", "text": "Subscribed to Cult.fit gym membership for 1 year."},
            {"date": "2025-03-01", "text": "Canceled Cult.fit subscription. Joined YMCA for badminton and swimming."}
        ],
        "query": "Which fitness club or sports center am I currently attending?",
        "v1_expected_failure": "Cult.fit and YMCA",
        "v2_expected_ground_truth": "YMCA",
        "obsolete_entities": ["Cult.fit"],
        "active_entities": ["YMCA"]
    },

    # =========================================================================
    # 2. POINT-IN-TIME HISTORICAL QUERIES (5 CASES)
    # =========================================================================
    {
        "id": "TKG_07",
        "category": "point_in_time",
        "description": "Historical employment lookup at specific past date",
        "events": [
            {"date": "2023-01-01", "text": "Rahul worked at Swiggy from January 2023 to December 2024."},
            {"date": "2025-01-01", "text": "Rahul started working at Google in January 2025."}
        ],
        "query": "Where was Rahul working on July 15, 2024?",
        "target_date": "2024-07-15",
        "v1_expected_failure": "Google (or confounds July 2024 with current Google role)",
        "v2_expected_ground_truth": "Swiggy",
        "obsolete_entities": ["Google"],
        "active_entities": ["Swiggy"]
    },
    {
        "id": "TKG_08",
        "category": "point_in_time",
        "description": "Historical residency lookup at past date",
        "events": [
            {"date": "2022-01-01", "text": "Rachit lived in Chennai until January 2025."},
            {"date": "2025-02-01", "text": "Rachit relocated to Bangalore in February 2025."}
        ],
        "query": "Where did Rachit live in 2023?",
        "target_date": "2023-06-01",
        "v1_expected_failure": "Bangalore or both Chennai and Bangalore",
        "v2_expected_ground_truth": "Chennai",
        "obsolete_entities": ["Bangalore"],
        "active_entities": ["Chennai"]
    },
    {
        "id": "TKG_09",
        "category": "point_in_time",
        "description": "Project manager assignment at past milestone",
        "events": [
            {"date": "2024-01-01", "text": "Priya was lead manager of Project Apex from Jan to June 2024."},
            {"date": "2024-07-01", "text": "Karthik took over as lead manager of Project Apex in July 2024."}
        ],
        "query": "Who was managing Project Apex in March 2024?",
        "target_date": "2024-03-15",
        "v1_expected_failure": "Karthik (most recent manager)",
        "v2_expected_ground_truth": "Priya",
        "obsolete_entities": ["Karthik"],
        "active_entities": ["Priya"]
    },
    {
        "id": "TKG_10",
        "category": "point_in_time",
        "description": "Doctor / Clinic consultation history",
        "events": [
            {"date": "2023-05-01", "text": "Prasad Appa was consulting Dr. Mehta at Apollo until late 2024."},
            {"date": "2025-01-10", "text": "Prasad Appa switched to Dr. Sundaram at Fortis Hospital."}
        ],
        "query": "Which doctor was Appa seeing in November 2023?",
        "target_date": "2023-11-20",
        "v1_expected_failure": "Dr. Sundaram at Fortis",
        "v2_expected_ground_truth": "Dr. Mehta at Apollo",
        "obsolete_entities": ["Dr. Sundaram", "Fortis"],
        "active_entities": ["Dr. Mehta", "Apollo"]
    },
    {
        "id": "TKG_11",
        "category": "point_in_time",
        "description": "College student degree phase",
        "events": [
            {"date": "2021-08-01", "text": "Ananya was an undergraduate student at IIT Madras until May 2025."},
            {"date": "2025-08-01", "text": "Ananya started her PhD at Stanford University."}
        ],
        "query": "Where was Ananya studying in September 2024?",
        "target_date": "2024-09-15",
        "v1_expected_failure": "Stanford University",
        "v2_expected_ground_truth": "IIT Madras",
        "obsolete_entities": ["Stanford University", "Stanford"],
        "active_entities": ["IIT Madras"]
    },

    # =========================================================================
    # 3. MULTI-HOP RELATIONAL TRAVERSAL (THE NETWORK PROBLEM) - 5 CASES
    # =========================================================================
    {
        "id": "TKG_12",
        "category": "multi_hop_traversal",
        "description": "2-Hop Referral Discovery: Me -> Appa -> Ramesh -> Bosch",
        "events": [
            {"date": "2024-02-10", "text": "Prasad Appa introduced me to his engineering college friend Ramesh."},
            {"date": "2024-08-15", "text": "Ramesh joined Bosch as Vice President of Embedded Systems."},
            {"date": "2025-03-01", "text": "Looking for firmware engineering referral opportunities."}
        ],
        "query": "Who in my personal network is connected to Bosch?",
        "v1_expected_failure": "No matches found (or searches only for 'Bosch' and misses Ramesh/Appa connection)",
        "v2_expected_ground_truth": "Ramesh (friend of Prasad Appa)",
        "expected_path": ["Ashwin", "Prasad Appa", "Ramesh", "Bosch"],
        "target_entity": "Ramesh"
    },
    {
        "id": "TKG_13",
        "category": "multi_hop_traversal",
        "description": "2-Hop Landlord / Flat resolution",
        "events": [
            {"date": "2024-05-01", "text": "Madhu introduced me to Suresh uncle."},
            {"date": "2024-06-10", "text": "Suresh uncle owns GreenView Apartments flat 302 in Indiranagar."}
        ],
        "query": "Who owns the apartment in Indiranagar that Madhu told me about?",
        "v1_expected_failure": "Fails to associate Madhu with GreenView Apartments owner Suresh",
        "v2_expected_ground_truth": "Suresh uncle",
        "expected_path": ["Madhu", "Suresh uncle", "GreenView Apartments"],
        "target_entity": "Suresh uncle"
    },
    {
        "id": "TKG_14",
        "category": "multi_hop_traversal",
        "description": "3-Hop Venture Capital / Investor network",
        "events": [
            {"date": "2023-11-01", "text": "Ashwin collaborates with Rachit on open source."},
            {"date": "2024-03-15", "text": "Rachit's co-founder is Neha."},
            {"date": "2024-09-20", "text": "Neha's mentor is Kunal Shah at QED Ventures."}
        ],
        "query": "Can we reach Kunal Shah through our engineering network?",
        "v1_expected_failure": "Direct search on Kunal Shah returns no direct relation to Ashwin",
        "v2_expected_ground_truth": "Yes, via Rachit -> Neha -> Kunal Shah",
        "expected_path": ["Ashwin", "Rachit", "Neha", "Kunal Shah"],
        "target_entity": "Kunal Shah"
    },
    {
        "id": "TKG_15",
        "category": "multi_hop_traversal",
        "description": "Gift / Preference tracking across family",
        "events": [
            {"date": "2024-04-12", "text": "Amma mentioned that her sister Chachi loves Darjeeling First Flush tea."},
            {"date": "2025-02-14", "text": "Visiting Chachi for her birthday next week."}
        ],
        "query": "What gift did Amma recommend for Chachi?",
        "v1_expected_failure": "Fails to link birthday visit with tea preference from months ago",
        "v2_expected_ground_truth": "Darjeeling First Flush tea",
        "expected_path": ["Amma", "Chachi", "Darjeeling First Flush tea"],
        "target_entity": "Darjeeling First Flush tea"
    },
    {
        "id": "TKG_16",
        "category": "multi_hop_traversal",
        "description": "Tech Stack Dependency & Service Owner",
        "events": [
            {"date": "2024-07-01", "text": "Payments service is maintained by Karthik."},
            {"date": "2024-10-15", "text": "Payments service is crashing due to Postgres connection pool exhaustion."}
        ],
        "query": "Who is responsible for fixing the Postgres connection crashes?",
        "v1_expected_failure": "Only highlights Postgres without identifying Karthik as the owner",
        "v2_expected_ground_truth": "Karthik (Payments service owner)",
        "expected_path": ["Postgres crash", "Payments service", "Karthik"],
        "target_entity": "Karthik"
    },

    # =========================================================================
    # 4. STATE CONTRADICTION & CANCELLATION (5 CASES)
    # =========================================================================
    {
        "id": "TKG_17",
        "category": "contradiction_resolution",
        "description": "Flight booking rescheduled and then canceled",
        "events": [
            {"date": "2025-08-01 10:00", "text": "Booked IndiGo flight 6E-204 to Mumbai for Friday 10 AM."},
            {"date": "2025-08-02 14:00", "text": "IndiGo rescheduled flight 6E-204 to Friday 4 PM."},
            {"date": "2025-08-03 09:00", "text": "Mumbai meeting canceled. Canceled IndiGo flight 6E-204 completely."}
        ],
        "query": "What time is my flight to Mumbai on Friday?",
        "v1_expected_failure": "Friday 10 AM or Friday 4 PM (does not recognize cancellation)",
        "v2_expected_ground_truth": "The flight is canceled (no active flight)",
        "obsolete_entities": ["10 AM", "4 PM", "6E-204"],
        "active_entities": ["canceled"]
    },
    {
        "id": "TKG_18",
        "category": "contradiction_resolution",
        "description": "Dinner meeting venue change",
        "events": [
            {"date": "2025-09-10 11:00", "text": "Dinner with client scheduled at Taj Coromandel at 8 PM."},
            {"date": "2025-09-10 16:30", "text": "Client requested change of venue to ITC Grand Chola at 8:30 PM."}
        ],
        "query": "Where am I meeting the client for dinner tonight and at what time?",
        "v1_expected_failure": "Taj Coromandel at 8 PM or mentions both hotels",
        "v2_expected_ground_truth": "ITC Grand Chola at 8:30 PM",
        "obsolete_entities": ["Taj Coromandel", "8 PM"],
        "active_entities": ["ITC Grand Chola", "8:30 PM"]
    },
    {
        "id": "TKG_19",
        "category": "contradiction_resolution",
        "description": "Medical prescription dosage revision",
        "events": [
            {"date": "2024-11-01", "text": "Doctor prescribed Metformin 500mg once daily after breakfast."},
            {"date": "2025-02-15", "text": "Doctor increased dosage: take Metformin 1000mg twice daily."}
        ],
        "query": "What is my current prescribed dosage of Metformin?",
        "v1_expected_failure": "500mg once daily and 1000mg twice daily",
        "v2_expected_ground_truth": "1000mg twice daily",
        "obsolete_entities": ["500mg once daily"],
        "active_entities": ["1000mg twice daily"]
    },
    {
        "id": "TKG_20",
        "category": "contradiction_resolution",
        "description": "AWS Cloud migration canceled in favor of GCP",
        "events": [
            {"date": "2024-04-01", "text": "Decided to migrate infrastructure from on-prem to AWS by Q4."},
            {"date": "2024-08-20", "text": "Aborted AWS migration due to pricing. Fully committed to GCP migration."}
        ],
        "query": "Which cloud provider are we migrating our infrastructure to?",
        "v1_expected_failure": "AWS and GCP",
        "v2_expected_ground_truth": "GCP",
        "obsolete_entities": ["AWS"],
        "active_entities": ["GCP"]
    },
    {
        "id": "TKG_21",
        "category": "contradiction_resolution",
        "description": "House purchase offer rejected and retracted",
        "events": [
            {"date": "2025-05-01", "text": "Made an offer of 1.2 Crore for the apartment in Adyar."},
            {"date": "2025-05-10", "text": "Seller refused 1.2 Cr offer. Retracted the offer and stopped negotiations."}
        ],
        "query": "Do we have an active offer on the Adyar property?",
        "v1_expected_failure": "Yes, an offer of 1.2 Crore is active",
        "v2_expected_ground_truth": "No, the offer was retracted and negotiations stopped",
        "obsolete_entities": ["1.2 Crore active offer"],
        "active_entities": ["retracted", "no active offer"]
    },

    # =========================================================================
    # 5. CONTACT ATTRIBUTE MUTATION (PHONE & EMAIL UPDATES) - 4 CASES
    # =========================================================================
    {
        "id": "TKG_22",
        "category": "attribute_mutation",
        "description": "Primary phone number update",
        "events": [
            {"date": "2023-01-01", "text": "Ananya's phone number is 9840112345."},
            {"date": "2025-01-10", "text": "Ananya lost her old phone. Her new primary mobile is 9710099888. Do not use the old number."}
        ],
        "query": "What phone number should I use to call Ananya?",
        "v1_expected_failure": "9840112345 or provides both numbers",
        "v2_expected_ground_truth": "9710099888",
        "obsolete_entities": ["9840112345"],
        "active_entities": ["9710099888"]
    },
    {
        "id": "TKG_23",
        "category": "attribute_mutation",
        "description": "Email address change from university to corporate",
        "events": [
            {"date": "2022-08-01", "text": "Email Rohit at rohit@iitm.ac.in for research notes."},
            {"date": "2024-07-01", "text": "Rohit graduated. His new active email is rohit@microsoft.com."}
        ],
        "query": "What is Rohit's current email address?",
        "v1_expected_failure": "rohit@iitm.ac.in and rohit@microsoft.com",
        "v2_expected_ground_truth": "rohit@microsoft.com",
        "obsolete_entities": ["rohit@iitm.ac.in"],
        "active_entities": ["rohit@microsoft.com"]
    },
    {
        "id": "TKG_24",
        "category": "attribute_mutation",
        "description": "Bank account IFSC / account number change",
        "events": [
            {"date": "2023-03-01", "text": "Landlord bank account for rent is HDFC Bank A/C 501002345678."},
            {"date": "2024-12-01", "text": "Landlord closed HDFC account. Send rent to ICICI Bank A/C 001205009999."}
        ],
        "query": "Which bank account should I transfer rent to?",
        "v1_expected_failure": "HDFC Bank A/C 501002345678",
        "v2_expected_ground_truth": "ICICI Bank A/C 001205009999",
        "obsolete_entities": ["HDFC Bank", "501002345678"],
        "active_entities": ["ICICI Bank", "001205009999"]
    },
    {
        "id": "TKG_25",
        "category": "attribute_mutation",
        "description": "Wi-Fi password rotation",
        "events": [
            {"date": "2024-01-01", "text": "Home Wi-Fi password is 'Welcome2024!'"},
            {"date": "2025-01-01", "text": "Updated home router Wi-Fi password to 'TitanSecure#2025'."}
        ],
        "query": "What is the current home Wi-Fi password?",
        "v1_expected_failure": "Welcome2024!",
        "v2_expected_ground_truth": "TitanSecure#2025",
        "obsolete_entities": ["Welcome2024!"],
        "active_entities": ["TitanSecure#2025"]
    }
]
