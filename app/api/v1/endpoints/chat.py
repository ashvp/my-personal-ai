from fastapi import APIRouter, Depends, status
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.llm_service import OllamaLLMService, get_llm_service
from app.core.security import verify_device_token

router = APIRouter()


@router.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Chat with personal assistant",
    description=(
        "Protected chat endpoint. Requires a valid 'X-Device-Token' header. "
        "Accepts a user message and returns the response from the local Qwen model."
    ),
    dependencies=[Depends(verify_device_token)]
)
async def chat_endpoint(
    request: ChatRequest,
    llm: OllamaLLMService = Depends(get_llm_service)
) -> ChatResponse:
    """Chat endpoint for querying the local Qwen model from authorized devices."""
    return await llm.generate_reply(request)
