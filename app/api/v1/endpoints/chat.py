from fastapi import APIRouter, Depends, status
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.llm_service import OllamaLLMService, get_llm_service

router = APIRouter()


@router.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Chat with local Qwen model",
    description="Accepts user message, optional conversation history, and queries the local Qwen model via Ollama to return a reply."
)
async def chat_endpoint(
    request: ChatRequest,
    llm: OllamaLLMService = Depends(get_llm_service)
) -> ChatResponse:
    """Chat endpoint for querying the local Qwen model.

    - **message**: Prompt / query to send to the assistant.
    - **system_prompt**: Optional customized system persona or instructions.
    - **history**: Optional previous messages for multi-turn conversations.
    - **temperature**: Optional randomness control (0.0 to 2.0).
    - **model**: Optional override for the target model.
    """
    return await llm.generate_reply(request)
