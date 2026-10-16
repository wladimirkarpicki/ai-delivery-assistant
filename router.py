from providers.openrouter_provider import OpenRouterProvider


class ModelRouter:
    """
    Routes requests to the correct LLM provider.
    """

    def __init__(self):

        self.provider_classes = {
            "openrouter": OpenRouterProvider,
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

    def embed_texts(
        self,
        provider,
        model,
        texts,
    ):
        """
        Embed texts with the provider's embedding model.

        Args:
            provider (str): provider name
            model (str): embedding model identifier
            texts (list[str]): texts to embed

        Returns:
            list[list[float]]: one embedding vector per input text
        """

        selected_provider = self._get_provider(provider)

        return selected_provider.embed_texts(
            model=model,
            texts=texts,
        )
