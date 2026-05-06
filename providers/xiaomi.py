import os
from .base import OpenAICompatibleProvider


class XiaomiProvider(OpenAICompatibleProvider):
    """小米 (MIMO) API Provider"""

    def __init__(self, api_key=None, model="mimo-v2.5", base_url=None):
        super().__init__(
            api_key=api_key or os.getenv("XIAOMI_API_KEY"),
            base_url=base_url or os.getenv("XIAOMI_BASE_URL", "https://api.mimo.ai/v1"),
            model=model
        )

