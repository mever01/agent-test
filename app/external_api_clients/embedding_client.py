import httpx

from core.utils.mixins.logger import LoggerMixin
from app.configs import settings


class EmbeddingClient(LoggerMixin):
    def __init__(
        self,
        url: str | None = None,
        model_name: str | None = None,
        dimension: int | None = None,
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.url = (
            settings.embedding.url if url is None else url
        )
        self.model_name = (
            settings.embedding.model_name
            if model_name is None else model_name
        )
        self.dimension = (
            settings.embedding.dimension
            if dimension is None else dimension
        )
        self.api_key = (
            settings.embedding.api_key
            if api_key is None else api_key
        )

        headers = {
            "Content-Type": "application/json",
        }

        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers=headers,
        )

    async def get_embedding(
        self,
        text: str,
        instruction: str | None = None,
    ) -> list[float]:
        """Получает embedding одного текста."""

        prompt = (
            f"Instruct: {instruction}\nQuery: {text}"
            if instruction
            else text
        )

        if "/api/embeddings" in self.url:
            payload = {
                "model": self.model_name,
                "prompt": prompt,
            }
        else:
            payload = {
                "model": self.model_name,
                "input": prompt,
            }

        try:
            response = await self._client.post(
                self.url,
                json=payload,
            )
            response.raise_for_status()

            data = response.json()

            if data.get("data"):
                embedding = data["data"][0]["embedding"]
            elif "embedding" in data:
                embedding = data["embedding"]
            else:
                raise ValueError(
                    "Unexpected embedding response format"
                )

            if (
                self.dimension is not None
                and len(embedding) != self.dimension
            ):
                raise ValueError(
                    f"Invalid embedding dimension: "
                    f"expected={self.dimension}, "
                    f"actual={len(embedding)}"
                )

            return embedding

        except Exception:
            self.logger.exception(
                "Embedding request failed: url=%s, model=%s",
                self.url,
                self.model_name,
            )
            raise

    async def get_embeddings(
        self,
        texts: list[str],
        instruction: str | None = None,
    ) -> list[list[float]]:
        """Получает embeddings для нескольких текстов."""

        results = []

        for text in texts:
            embedding = await self.get_embedding(
                text,
                instruction=instruction,
            )
            results.append(embedding)

        return results

    async def close(self) -> None:
        await self._client.aclose()
