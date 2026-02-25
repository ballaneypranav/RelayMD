from __future__ import annotations

import httpx


class SaladScaler:
    def __init__(
        self,
        organization_name: str,
        project_name: str,
        container_group_name: str,
        api_key: str,
        max_replicas: int = 4,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.organization_name = organization_name
        self.project_name = project_name
        self.container_group_name = container_group_name
        self.api_key = api_key
        self.max_replicas = max_replicas
        self.timeout_seconds = timeout_seconds

    @property
    def _url(self) -> str:
        return (
            "https://api.salad.com/api/public/organizations/"
            f"{self.organization_name}/projects/{self.project_name}/containers/{self.container_group_name}"
        )

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def get_current_replicas(self) -> int:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(self._url, headers=self._headers)
            response.raise_for_status()
            payload = response.json()
        return int(payload["replicas"])

    async def scale(self, target: int) -> None:
        bounded_target = max(0, min(target, self.max_replicas))
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.patch(
                self._url,
                headers=self._headers,
                json={"replicas": bounded_target},
            )
            response.raise_for_status()
