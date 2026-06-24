"""
Day 3: 模型对接
支持 Ollama 本地 + DeepSeek API 双模式
"""
import os
from enum import Enum
from dotenv import load_dotenv
from openai import OpenAI
from app.common.logger import logger

load_dotenv()


class ModelSource(str, Enum):
    OLLAMA = "ollama"
    DEEPSEEK = "deepseek"


class ModelHandler:
    """统一模型调用接口"""

    def __init__(self):
        self.ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")
        self.ollama_client = OpenAI(
            base_url="http://localhost:11434/v1",
            api_key="ollama"  # Ollama 不需要真的 key
        )

        self.deepseek_client = None
        deepseek_key = os.getenv("DEEPSEEK_API_KEY", "")
        if deepseek_key:
            self.deepseek_client = OpenAI(
                base_url="https://api.deepseek.com",
                api_key=deepseek_key
            )

    def chat(self, messages: list[dict], source: ModelSource = ModelSource.OLLAMA, stream: bool = True):
        """
        统一对话接口
        - source=ollama: 本地模型，数据不出门
        - source=deepseek: 云端 API，更快更强
        """
        if source == ModelSource.DEEPSEEK and self.deepseek_client:
            client = self.deepseek_client
            model = "deepseek-chat"
            logger.info("使用 DeepSeek API")
        else:
            client = self.ollama_client
            model = self.ollama_model
            logger.info(f"使用本地 Ollama: {model}")

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            stream=stream
        )

        if stream:
            return response  # 返回迭代器，调用方自行 SSE
        else:
            return response.choices[0].message.content
