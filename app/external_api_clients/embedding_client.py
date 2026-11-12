import httpx
import logging
from app.configs import settings

logger = logging.getLogger(__name__)

class EmbeddingClient:
    def __init__(
        self,
        url: str | None = None,
        model_name: str | None = None,
        dimension: int | None = None,
        api_key: str | None = None,
        timeout: float = 30.0,
    ):
        self.url = url or settings.embedding.url
        self.model_name = model_name or settings.embedding.model_name
        self.dimension = dimension or settings.embedding.dimension
        self.api_key = api_key or settings.embedding.api_key
        self.timeout = timeout

    async def get_embedding(self, text: str, instruction: str | None = None) -> list[float]:
        """
        Получение эмбеддинга для одного текста.
        Поддерживает Qwen3-Embedding instruction-aware формат.
        """
        headers = {"Content-Type": "application/json"}
        if self.api_key and self.api_key.strip():
            headers["Authorization"] = f"Bearer {self.api_key}"

        prompt = f"Instruct: {instruction}\nQuery: {text}" if instruction else text

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                # 1. Попытка вызвать Ollama native /api/embeddings формат
                if "/api/embeddings" in self.url:
                    payload = {"model": self.model_name, "prompt": prompt}
                else:
                    # 2. Стандартный OpenAI формат (/v1/embeddings)
                    payload = {"model": self.model_name, "input": prompt}

                response = await client.post(self.url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()

                if "data" in data and len(data["data"]) > 0:
                    return data["data"][0]["embedding"]
                elif "embedding" in data:
                    return data["embedding"]
                else:
                    raise ValueError(f"Неожиданный формат ответа эмбеддера: {data}")
            except Exception as e:
                logger.error(f"Ошибка вызова сервиса эмбеддингов по адресу {self.url}: {e}")
                # Если сервис недоступен в изоляции, выбрасываем ошибку
                raise e

    async def get_embeddings(self, texts: list[str], instruction: str | None = None) -> list[list[float]]:
        """Пакетное получение эмбеддингов."""
        results = []
        for t in texts:
            emb = await self.get_embedding(t, instruction=instruction)
            results.append(emb)
        return results

