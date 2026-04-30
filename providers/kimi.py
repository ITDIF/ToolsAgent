
import os
from .base import OpenAICompatibleProvider


class KimiProvider(OpenAICompatibleProvider):
    """Kimi (月之暗面) API Provider"""

    def __init__(self, api_key=None, model="moonshot-v1-8k"):
        super().__init__(
            api_key=api_key or os.getenv("KIMI_API_KEY"),
            base_url="https://api.moonshot.cn/v1",
            model=model
        )

