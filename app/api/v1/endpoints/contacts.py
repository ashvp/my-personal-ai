from typing import Optional
from fastapi import APIRouter, Query, status
from pydantic import BaseModel

from app.services.contacts_service import contacts_service
from app.services.memory_service import memory_service

router = APIRouter(prefix="/contacts", tags=["Contacts & Calling"])


class ContactSyncResponse(BaseModel):
    success: bool
    synced_count: Optional[int] = 0
    named_contacts: Optional[int] = 0
    message: str


@router.post("/sync", response_model=ContactSyncResponse, summary="Sync contacts from Beeper into DuckDB")
async def sync_contacts():
    """Syncs contacts and phone identifiers from local Beeper SQLite store into DuckDB."""
    result = contacts_service.sync_contacts()
    return result


@router.get("/status", summary="Check contacts service status")
async def get_contacts_status():
    """Returns availability and total count of indexed contacts."""
    return {
        "available": contacts_service.is_available(),
        "db_path": contacts_service.db_path,
        "total_contacts": memory_service.get_contact_count()
    }


@router.get("/search", summary="Search contacts by name or phone")
async def search_contacts(q: str = Query(..., min_length=1, description="Search term for name or phone number")):
    """Searches indexed contacts in DuckDB."""
    results = contacts_service.search_contacts(q)
    return {
        "query": q,
        "count": len(results),
        "results": results
    }


@router.post("/call", summary="Trigger autonomous phone call to a contact")
async def trigger_call(name: str = Query(..., min_length=1, description="Contact name to call")):
    """Autonomously dials the contact on your phone SIM via MacroDroid."""
    card_md = await contacts_service.initiate_call_card(name)
    contact = contacts_service.find_contact(name)
    return {
        "query": name,
        "found": contact is not None,
        "contact": contact,
        "card_markdown": card_md
    }


@router.get("/card", summary="Generate a call card for a contact")
async def get_call_card(name: str = Query(..., min_length=1, description="Contact name to generate call card for")):
    """Generates markdown card with cellular call and messaging options."""
    card_md = await contacts_service.initiate_call_card(name)
    contact = contacts_service.find_contact(name)
    return {
        "query": name,
        "found": contact is not None,
        "contact": contact,
        "card_markdown": card_md
    }
