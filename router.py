from providers.google_provider import GoogleProvider
from providers.groq_provider import GroqProvider


class ModelRouter:
    """
    Routes requests to the correct LLM provider.
    """

    def __init__(self):

        self.provider_classes = {
            "google": GoogleProvider,
            "groq": GroqProvider,
        }
        self.providers = {}

    def _get_provider(self, provider):
        if provider not in self.provider_classes:
            raise ValueError(f"Unsupported provider: {provider}")

        if provider not in self.providers:
            self.providers[provider] = self.provider_classes[provider]()

        return self.providers[provider]


    def generate(
        self,
        provider,
        model,
        prompt
    ):
        """
        Send request to selected provider.

        Args:
            provider (str): provider name
            model (str): model identifier
            prompt (str): input prompt

        Returns:
            str: generated response
        """

        selected_provider = self._get_provider(provider)


        return selected_provider.generate(
            model=model,
            prompt=prompt
        )


    def get_models(self, provider):
        """
        Return available models for provider.
        """

        selected_provider = self._get_provider(provider)


        return selected_provider.get_models()
