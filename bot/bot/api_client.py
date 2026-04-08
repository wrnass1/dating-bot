import httpx


class ApiClient:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=10.0)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def upsert_telegram_user(
        self,
        *,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        language: str | None,
    ) -> dict:
        resp = await self._client.post(
            "/users/telegram/upsert",
            json={
                "telegram_id": telegram_id,
                "username": username,
                "first_name": first_name,
                "language": language,
            },
        )
        resp.raise_for_status()
        return resp.json()

