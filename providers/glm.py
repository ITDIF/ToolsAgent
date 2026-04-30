import os
from .base import OpenAICompatibleProvider


class GlmProvider(OpenAICompatibleProvider):
    """GLM (智谱 AI) API Provider"""

    def __init__(self, api_key=None, model="glm-4"):
        super().__init__(
            api_key=api_key or os.getenv("GLM_API_KEY"),
            base_url="https://open.bigmodel.cn/api/paas/v4/",
            model=model
        )

