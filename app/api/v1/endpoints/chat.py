from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse

from app.schemas.chat import ChatRequest, ChatResponse
from app.services.llm_service import OllamaLLMService, get_llm_service
from app.core.security import verify_device_token

router = APIRouter()


@router.post(
    "/chat",
    summary="Chat with personal assistant (Streaming by default)",
    description=(
        "Protected chat endpoint for your personal devices.\n\n"
        "- **Default (stream=true)**: Streams response tokens in real-time via Server-Sent Events (SSE) `text/event-stream`.\n"
        "- **Blocking (stream=false)**: Returns a complete JSON object once finished."
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
async def chat_endpoint(
    request: ChatRequest,
    llm: OllamaLLMService = Depends(get_llm_service)
):
    """Chat endpoint supporting real-time streaming and blocking JSON responses."""
    if request.stream:
        return StreamingResponse(
            llm.stream_reply(prompt=request.message),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disables proxy buffering (ngrok, nginx)
            }
        )

    # Blocking JSON response for internal tasks or when stream=false
    return await llm.generate_reply(prompt=request.message)
