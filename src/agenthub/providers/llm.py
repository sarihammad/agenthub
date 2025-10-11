"""LLM provider interface and OpenAI implementation."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from agenthub.config import settings


class LLMProvider(ABC):
    """Abstract LLM provider interface."""

    @abstractmethod
    async def complete(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Generate a completion.
        
        Args:
            messages: List of message dicts with role and content
            tools: Optional list of tool definitions for function calling
            temperature: Sampling temperature
            max_tokens: Max tokens to generate
            
        Returns:
            Dict with 'content', 'tool_calls', 'tokens_in', 'tokens_out'
        """
        pass

    @abstractmethod
    async def complete_stream(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
    ) -> Any:
        """Generate a streaming completion.
        
        Args:
            messages: List of message dicts
            tools: Optional tool definitions
            temperature: Sampling temperature
            
        Yields:
            Chunks of the response
        """
        pass


class OpenAIProvider(LLMProvider):
    """OpenAI LLM provider."""

    def __init__(self, api_key: str, model: str) -> None:
        """Initialize OpenAI provider.
        
        Args:
            api_key: OpenAI API key
            model: Model name
        """
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def complete(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Generate a completion using OpenAI."""
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        if max_tokens:
            kwargs["max_tokens"] = max_tokens

        response = await self.client.chat.completions.create(**kwargs)

        result: Dict[str, Any] = {
            "content": "",
            "tool_calls": [],
            "tokens_in": response.usage.prompt_tokens if response.usage else 0,
            "tokens_out": response.usage.completion_tokens if response.usage else 0,
        }

        if response.choices:
            choice = response.choices[0]
            if choice.message.content:
                result["content"] = choice.message.content

            if choice.message.tool_calls:
                result["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in choice.message.tool_calls
                ]

        return result

    async def complete_stream(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
    ) -> Any:
        """Generate a streaming completion using OpenAI."""
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        stream = await self.client.chat.completions.create(**kwargs)

        async for chunk in stream:
            if chunk.choices:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield {"type": "content", "data": delta.content}
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        yield {"type": "tool_call", "data": tc}


def get_llm_provider(provider: str = "openai") -> LLMProvider:
    """Get an LLM provider instance.
    
    Args:
        provider: Provider name (default: openai)
        
    Returns:
        LLM provider instance
    """
    if provider == "openai":
        return OpenAIProvider(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
        )
    else:
        raise ValueError(f"Unknown provider: {provider}")

