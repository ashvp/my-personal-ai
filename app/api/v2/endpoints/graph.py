from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.security import verify_device_token
from app.services.graph_service import GraphService, get_graph_service

router = APIRouter(prefix="/graph", tags=["Knowledge Graph (v2)"])


class FactAssertionRequest(BaseModel):
    subject: str = Field(..., description="Source entity name, e.g. 'Rahul'")
    predicate: str = Field(..., description="Relationship type, e.g. 'WORKS_AT'")
    object: str = Field(..., description="Target entity or attribute value, e.g. 'Google'")
    valid_from: str = Field(..., description="ISO date or datetime string when this fact became valid, e.g. '2025-01-15'")
    source_id: Optional[str] = Field("", description="Originating message ID or source identifier")
    confidence: Optional[float] = Field(1.0, ge=0.0, le=1.0, description="Confidence score")
    is_terminal_mutation: Optional[bool] = Field(None, description="Whether this assertion invalidates previous values of same predicate")


@router.post(
    "/assert",
    summary="Assert a temporal fact into the Knowledge Graph (v2)",
    description="Inserts an edge and automatically invalidates conflicting prior active edges if is_terminal_mutation is true.",
    dependencies=[Depends(verify_device_token)]
)
async def assert_fact_endpoint(
    req: FactAssertionRequest,
    graph: GraphService = Depends(get_graph_service)
):
    try:
        edge = graph.assert_fact(
            subject=req.subject,
            predicate=req.predicate,
            object=req.object,
            valid_from=req.valid_from,
            source_id=req.source_id,
            confidence=req.confidence or 1.0,
            is_terminal_mutation=req.is_terminal_mutation
        )
        return {"success": True, "edge": edge}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get(
    "/facts",
    summary="Query active or point-in-time facts (v2)",
    description="If target_date is supplied, performs a bitemporal slice (valid_from <= target_date <= valid_to). Otherwise, returns currently active facts (valid_to IS NULL).",
    dependencies=[Depends(verify_device_token)]
)
async def query_facts_endpoint(
    subject: Optional[str] = Query(None, description="Filter by subject entity"),
    predicate: Optional[str] = Query(None, description="Filter by relationship predicate"),
    object: Optional[str] = Query(None, description="Filter by object entity or attribute"),
    target_date: Optional[str] = Query(None, description="Historical point-in-time date (YYYY-MM-DD)"),
    graph: GraphService = Depends(get_graph_service)
):
    if target_date:
        facts = graph.query_point_in_time(
            target_date=target_date,
            subject=subject,
            predicate=predicate,
            object=object
        )
    else:
        facts = graph.query_active_facts(
            subject=subject,
            predicate=predicate,
            object=object
        )
    return {"total": len(facts), "target_date": target_date or "ACTIVE", "facts": facts}


@router.get(
    "/traverse",
    summary="Multi-hop Breadth-First Search (BFS) path traversal (v2)",
    description="Finds the shortest relational path between two entities in the knowledge graph.",
    dependencies=[Depends(verify_device_token)]
)
async def traverse_endpoint(
    start: str = Query(..., description="Start entity name, e.g. 'Ashwin'"),
    target: str = Query(..., description="Target entity name, e.g. 'Kunal Shah'"),
    max_depth: int = Query(4, ge=1, le=10, description="Maximum hops to explore"),
    target_date: Optional[str] = Query(None, description="Optional point-in-time date filter"),
    graph: GraphService = Depends(get_graph_service)
):
    path = graph.traverse_network(start_entity=start, target_entity=target, max_depth=max_depth, target_date=target_date)
    if path is None:
        return {"connected": False, "hops": 0, "path": []}
    return {"connected": True, "hops": len(path), "path": path}


@router.get(
    "/entities",
    summary="Search entities in the knowledge graph (v2)",
    dependencies=[Depends(verify_device_token)]
)
async def search_entities_endpoint(
    query: str = Query("", description="Search term for entity name or alias"),
    limit: int = Query(20, ge=1, le=100),
    graph: GraphService = Depends(get_graph_service)
):
    results = graph.search_entities(query=query, limit=limit)
    return {"total": len(results), "entities": results}


@router.get(
    "/entity/{name}",
    summary="Get entity details and full historical timeline of facts (v2)",
    dependencies=[Depends(verify_device_token)]
)
async def get_entity_endpoint(
    name: str,
    graph: GraphService = Depends(get_graph_service)
):
    history = graph.query_entity_history(name)
    active = graph.query_active_facts(subject=name)
    return {
        "entity": name,
        "active_facts": active,
        "historical_timeline": history
    }
