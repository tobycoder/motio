from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
import logging
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen


@dataclass(slots=True)
class TenantSnapshot:
    """Lightweight dataset zodat bestaande code attributen kan blijven gebruiken."""

    id: str
    slug: str
    display_name: str
    status: str
    settings: dict[str, Any]
    branding: dict[str, Any]
    phrasing: dict[str, Any]
    contact_email: str | None

    def as_legacy(self) -> "LegacyTenant":
        return LegacyTenant(
            id=self.id,
            slug=self.slug,
            naam=self.display_name,
            settings=self.settings,
            status=self.status,
            branding=self.branding,
            phrasing=self.phrasing,
            contact_email=self.contact_email,
        )


@dataclass(slots=True)
class LegacyTenant:
    """Compatibel object voor bestaande templates (verwacht attributen zoals `.naam`)."""

    id: str
    slug: str
    naam: str
    settings: dict[str, Any]
    status: str
    branding: dict[str, Any]
    phrasing: dict[str, Any]
    contact_email: str | None


class TenantRegistryClient:
    """Eenvoudige HTTP-client met in-memory cache voor admotio metadata."""

    def __init__(
        self,
        *,
        base_url: str,
        api_token: str | None = None,
        tenant_id: str | None = None,
        timeout: float = 3.0,
        cache_ttl: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.tenant_id = tenant_id
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self._cache: dict[str, tuple[float, Optional[TenantSnapshot]]] = {}
        self._lock = threading.Lock()
        self._logger = logging.getLogger("app.tenant_registry")

    # ---------- Public API ----------
    def get_by_hostname(self, hostname: str) -> Optional[TenantSnapshot]:
        hostname = (hostname or "").strip().lower()
        if not hostname:
            return None
        cache_key = f"host:{hostname}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        endpoint = "tenants"
        query = urlencode({"hostname": hostname})
        payload = self._request_json(f"{endpoint}?{query}")
        tenant_data = None
        if payload and isinstance(payload.get("tenants"), list):
            tenant_data = next((item for item in payload["tenants"] if item.get("slug")), None)

        snapshot = self._parse_snapshot(tenant_data)
        self._cache_set(cache_key, snapshot)
        return snapshot

    def get_by_id(self, tenant_id: str) -> Optional[TenantSnapshot]:
        tenant_id = (tenant_id or "").strip()
        if not tenant_id:
            return None
        cache_key = f"id:{tenant_id}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        endpoint = f"tenants/{tenant_id}"
        payload = self._request_json(endpoint)
        snapshot = self._parse_snapshot(payload.get("tenant") if payload else None)
        self._cache_set(cache_key, snapshot)
        return snapshot

    def invalidate(self, tenant_id: str | None = None, hostname: str | None = None) -> None:
        with self._lock:
            if tenant_id:
                self._cache.pop(f"id:{tenant_id}", None)
            if hostname:
                self._cache.pop(f"host:{hostname.lower()}", None)
            if not tenant_id and not hostname:
                self._cache.clear()

    # ---------- Internal helpers ----------
    def _request_json(self, path: str) -> dict[str, Any] | None:
        url = urljoin(f"{self.base_url.rstrip('/')}/", path.lstrip("/"))
        headers = {"Accept": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        if self.tenant_id:
            headers["X-Tenant-ID"] = self.tenant_id
        request = Request(url, headers=headers)
        attempts = 2
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    if response.status >= 200 and response.status < 300:
                        raw = response.read()
                        if not raw:
                            return {}
                        return json.loads(raw.decode("utf-8"))
            except HTTPError as exc:
                if exc.code == 404:
                    self._logger.debug("Tenant registry gaf 404 voor %s", url)
                    return None
                self._logger.warning("Tenant registry HTTP fout (%s) voor %s (poging %s/%s)", exc.code, url, attempt, attempts)
                last_error = exc
            except URLError as exc:
                self._logger.warning("Tenant registry niet bereikbaar voor %s: %s (poging %s/%s)", url, exc, attempt, attempts)
                last_error = exc
            except (ValueError, json.JSONDecodeError) as exc:
                self._logger.warning("Tenant registry antwoord niet leesbaar voor %s: %s", url, exc)
                last_error = exc
                break
        if last_error:
            self._logger.debug("Tenant registry request mislukte na retries voor %s: %s", url, last_error)
        return None

    def _parse_snapshot(self, data: dict[str, Any] | None) -> Optional[TenantSnapshot]:
        if not data or "slug" not in data:
            return None
        settings = data.get("settings") or {}
        branding = data.get("branding") or {}
        phrasing = data.get("phrasing") or {}
        return TenantSnapshot(
            id=str(data.get("id") or ""),
            slug=str(data.get("slug")),
            display_name=str(data.get("display_name") or data.get("naam") or data.get("slug")),
            status=str(data.get("status") or "active"),
            settings=settings if isinstance(settings, dict) else {},
            branding=branding if isinstance(branding, dict) else {},
            phrasing=phrasing if isinstance(phrasing, dict) else {},
            contact_email=data.get("contact_email"),
        )

    def _cache_get(self, key: str) -> Optional[TenantSnapshot]:
        with self._lock:
            entry = self._cache.get(key)
        if not entry:
            return None
        expires_at, value = entry
        if expires_at < time.monotonic():
            with self._lock:
                self._cache.pop(key, None)
            return None
        return value

    def _cache_set(self, key: str, snapshot: Optional[TenantSnapshot]) -> None:
        expires_at = time.monotonic() + self.cache_ttl
        with self._lock:
            self._cache[key] = (expires_at, snapshot)
