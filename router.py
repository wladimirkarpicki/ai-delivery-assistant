from providers.google_provider import GoogleProvider
from providers.groq_provider import GroqProvider


class ModelRouter:
    """
    Routes requests to the correct LLM provider.
    """

    def __init__(self):

        self.providers = {
            "google": GoogleProvider(),
            "groq": GroqProvider()
        }


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

        if provider not in self.providers:
            raise ValueError(
                f"Unsupported provider: {provider}"
            )


        selected_provider = self.providers[provider]


        return selected_provider.generate(
            model=model,
            prompt=prompt
        )


    def get_models(self, provider):
        """
        Return available models for provider.
        """

        if provider not in self.providers:
            raise ValueError(
                f"Unsupported provider: {provider}"
            )


        selected_provider = self.providers[provider]


        return selected_provider.get_models()