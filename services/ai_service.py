"""Unified AI generation service."""
from router import ModelRouter

class AIService:
    def __init__(self, router=None):
        self.router = router or ModelRouter()

    def generate(self, provider: str, model: str, prompt: str) -> str:
        return self.router.generate(provider=provider, model=model, prompt=prompt)

    def list_models(self, provider: str):
        return self.router.get_models(provider)

