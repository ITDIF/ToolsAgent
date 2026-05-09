import os
from .base import OpenAICompatibleProvider


class GlmProvider(OpenAICompatibleProvider):
    """GLM (智谱 AI) API Provider"""

    def __init__(self, api_key=None, model="glm-4", base_url=None):
        super().__init__(
            api_key=api_key or os.getenv("GLM_API_KEY"),
            base_url=base_url or os.getenv("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"),
            model=model
        )
