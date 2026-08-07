import os
from typing import Literal, TypedDict

from openai import OpenAI


class ChatMessage(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


class OpenAICompatibleClient:
    """Call an LLM service that implements the OpenAI Chat Completions API."""

    def __init__(self, model: str, api_key: str, base_url: str) -> None:
        self.model = model
        self.provider = "auto"
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def invoke(self, messages: list[ChatMessage], **kwargs: object) -> str:
        """Return one complete response from an OpenAI-compatible service."""
        options = {key: value for key, value in kwargs.items() if key != "stream"}
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=False,
            **options,
        )
        answer = response.choices[0].message.content
        if not answer:
            raise RuntimeError("language model returned an empty response.")
        return answer

    def stream_invoke(
        self,
        messages: list[ChatMessage],
        **kwargs: object,
    ):
        """Yield response text chunks from an OpenAI-compatible service."""
        options = {key: value for key, value in kwargs.items() if key != "stream"}
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True,
            **options,
        )
        for chunk in response:
            content = chunk.choices[0].delta.content or ""
            if content:
                yield content

    def think(self, messages: list[ChatMessage]) -> str:
        """Generate one model response from an existing message list."""
        print("正在调用大语言模型...")
        try:
            answer = self.invoke(messages)
            print("大语言模型响应成功。")
            return answer
        except Exception as error:
            # Compatible providers can expose different SDK and transport errors.
            print(f"调用LLM API时发生错误：{error}")
            return "错误：调用语言模型服务时出错。"

    def generate(self, prompt: str, system_prompt: str) -> str:
        """Generate one model response for system and user prompts."""
        return self.think(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ]
        )


def create_llm_client_from_env() -> OpenAICompatibleClient:
    """Create the shared LLM client from required environment variables."""
    names = ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL_ID")
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        raise RuntimeError(f"缺少环境变量：{', '.join(missing)}")

    return OpenAICompatibleClient(
        model=os.environ["LLM_MODEL_ID"],
        api_key=os.environ["LLM_API_KEY"],
        base_url=os.environ["LLM_BASE_URL"],
    )


# Keep the Chapter 4 client behavior while adopting the Chapter 7 public name.
HelloAgentsLLM = OpenAICompatibleClient
