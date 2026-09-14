"""Local model adapter with explicit unavailable-state handling."""
import os
from enum import Enum
from threading import Lock

import httpx
from dotenv import load_dotenv
from openai import OpenAI

from app.common.logger import logger
from app.common.model_config import get_local_model_settings

load_dotenv()


class ModelSource(str, Enum):
    LOCAL = "local"
    OLLAMA = "local"


class _OfflineStreamChunk:
    def __init__(self, content: str):
        delta = type("Delta", (), {"content": content})()
        choice = type("Choice", (), {"delta": delta})()
        self.choices = [choice]


class _OfflineChatCompletions:
    def create(self, model: str, messages: list[dict], stream: bool = True):
        content = "离线模式：模型不可用（error_code=model_unavailable），未生成业务结论"
        if stream:
            return iter([_OfflineStreamChunk(content)])
        message = type("Msg", (), {"content": content})()
        choice = type("Choice", (), {"message": message})()
        return type("Resp", (), {"choices": [choice]})()


class _OfflineChatClient:
    def __init__(self):
        self.chat = type("Chat", (), {"completions": _OfflineChatCompletions()})()


class ModelHandler:
    """Unified local-model call boundary."""

    def __init__(self):
        local_settings = get_local_model_settings()
        self.local_model = local_settings.model_name
        self.ollama_model = self.local_model
        self.request_timeout = float(os.getenv("MODEL_REQUEST_TIMEOUT", "60"))
        from app.common.model_budget import default_model_budget

        self._budget = default_model_budget()
        try:
            self.local_client = OpenAI(
                base_url=local_settings.base_url,
                api_key=local_settings.api_key,
                http_client=self._build_http_client(local=True),
                max_retries=0,
            )
            self.ollama_client = self.local_client
        except Exception as exc:
            logger.warning(f"[Model] local model client unavailable: {exc}")
            self.local_client = _OfflineChatClient()
            self.ollama_client = self.local_client

    def _build_http_client(self, local: bool) -> httpx.Client:
        """Keep local model traffic independent of ambient proxy settings."""
        return httpx.Client(timeout=self.request_timeout, trust_env=False)

    def _rate_limited_response(self, stream: bool):
        content = (
            "Local model capacity is exhausted (error_code=rate_limited); "
            "no business conclusion was generated."
        )
        if stream:
            return iter([_OfflineStreamChunk(content)])
        return content

    def _release_after_stream(self, response, slot):
        try:
            yield from response
        finally:
            slot.release()

    def chat(self, messages: list[dict], source: ModelSource = ModelSource.LOCAL, stream: bool = True):
        """Call the local model; failures remain explicit and non-business results."""
        client = self.ollama_client
        model = self.local_model
        from app.common.model_budget import ModelBudgetExhausted

        try:
            slot = self._budget.acquire(wait_seconds=0)
        except ModelBudgetExhausted:
            logger.warning("[Model] local model concurrency budget exhausted")
            return self._rate_limited_response(stream)
        logger.info(f"使用内部本地模型: {model}")

        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                stream=stream,
            )
        except Exception as exc:
            slot.release()
            logger.warning(f"[Model] provider unavailable: {exc}")
            content = "离线模式：模型不可用（error_code=model_unavailable），未生成业务结论"
            if stream:
                return iter([_OfflineStreamChunk(content)])
            return content

        if stream:
            return self._release_after_stream(response, slot)
        try:
            return response.choices[0].message.content
        finally:
            slot.release()
