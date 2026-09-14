from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse

from app.schemas.chat import ChatRequest, ChatResponse
from app.services.llm_service import OllamaLLMService, get_llm_service
from app.core.security import verify_device_token

router = APIRouter()


@router.post(
    "/chat",
    summary="Chat with personal assistant (Version 2.0 with Bitemporal Knowledge Graph)",
    description=(
        "Version 2.0 (V2) Chat Endpoint:\n\n"
        "- Injects verified bitemporal knowledge graph ground truth into reasoning context.\n"
        "- Evaluates historical point-in-time constraints (e.g. 'Where did Rahul work in June 2024?').\n"
        "- Resolves multi-hop entity relationship chains before LLM inference.\n"
        "- Default (stream=true): Real-time Server-Sent Events (SSE) token stream.\n"
        "- Blocking (stream=false): Full JSON ChatResponse."
    ),
    dependencies=[Depends(verify_device_token)],
    responses={
        200: {
            "description": "SSE stream when stream=true, or JSON object when stream=false.",
            "content": {
                "text/event-stream": {
                    "example": 'data: {"token": "Hello", "done": false}\n\ndata: {"token": "", "done": true}\n\n'
                },
                "application/json": {
                    "schema": ChatResponse.model_json_schema()
                }
            }
        }
    }
)
async def chat_endpoint_v2(
    request: ChatRequest,
    llm: OllamaLLMService = Depends(get_llm_service)
):
    """V2 chat endpoint executing with version='v2' for Knowledge Graph prompt reasoning."""
    if request.stream:
        return StreamingResponse(
            llm.stream_reply(prompt=request.message, history=request.history, version="v2"),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "X-Assistant-Version": "v2",
            }
        )

    # Blocking JSON response with version='v2'
    return await llm.generate_reply(prompt=request.message, history=request.history, version="v2")
