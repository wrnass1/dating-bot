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

    async def upsert_profile(self, *, telegram_id: int, **fields) -> dict:
        resp = await self._client.post("/profiles/upsert", json={"telegram_id": telegram_id, **fields})
        resp.raise_for_status()
        return resp.json()

    async def get_profile(self, *, telegram_id: int) -> dict:
        resp = await self._client.get(f"/profiles/by_telegram/{telegram_id}")
        resp.raise_for_status()
        return resp.json()

    async def feed_next(self, *, telegram_id: int) -> dict:
        resp = await self._client.post("/feed/next", json={"telegram_id": telegram_id})
        resp.raise_for_status()
        return resp.json()

    async def interact(self, *, telegram_id: int, to_profile_id: str, action: str) -> dict:
        resp = await self._client.post(
            "/interactions",
            json={"telegram_id": telegram_id, "to_profile_id": to_profile_id, "action": action},
        )
        resp.raise_for_status()
        return resp.json()

    async def feed_action(self, *, telegram_id: int, to_profile_id: str, action: str) -> dict:
        resp = await self._client.post(
            "/feed/action",
            json={"telegram_id": telegram_id, "to_profile_id": to_profile_id, "action": action},
        )
        resp.raise_for_status()
        return resp.json()

