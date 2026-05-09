import os
from .base import OpenAICompatibleProvider


class DoubaoProvider(OpenAICompatibleProvider):
    """豆包 (字节跳动) API Provider"""

    def __init__(self, api_key=None, model="doubao-pro-32k", base_url=None):
        super().__init__(
            api_key=api_key or os.getenv("DOUBAO_API_KEY"),
            base_url=base_url or os.getenv("DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
            model=model
        )
