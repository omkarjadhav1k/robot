"""Reusable HTTP client pool with granular timeouts for sub-second external API calls."""

import httpx
from typing import Optional

# Reusable client for fast cloud AI reasoning (connect=2s, read=4s, write=2s, pool=2s)
_gemini_client: Optional[httpx.AsyncClient] = None

# Reusable client for general services (WhatsApp, webhooks, TTS)
_general_client: Optional[httpx.AsyncClient] = None


def get_gemini_http_client() -> httpx.AsyncClient:
    """Get or create singleton httpx.AsyncClient optimized for Gemini AI with generous timeouts."""
    global _gemini_client
    if _gemini_client is None or _gemini_client.is_closed:
        timeout = httpx.Timeout(connect=10.0, read=30.0, write=5.0, pool=5.0)
        limits = httpx.Limits(max_keepalive_connections=10, max_connections=20, keepalive_expiry=60.0)
        _gemini_client = httpx.AsyncClient(timeout=timeout, limits=limits)
    return _gemini_client


def get_general_http_client() -> httpx.AsyncClient:
    """Get or create singleton httpx.AsyncClient for WhatsApp, external TTS, and webhooks."""
    global _general_client
    if _general_client is None or _general_client.is_closed:
        timeout = httpx.Timeout(connect=3.0, read=12.0, write=5.0, pool=5.0)
        limits = httpx.Limits(max_keepalive_connections=10, max_connections=20, keepalive_expiry=60.0)
        _general_client = httpx.AsyncClient(timeout=timeout, limits=limits)
    return _general_client


async def close_http_clients():
    """Gracefully close all shared HTTP clients on application shutdown."""
    global _gemini_client, _general_client
    if _gemini_client and not _gemini_client.is_closed:
        await _gemini_client.aclose()
        _gemini_client = None
    if _general_client and not _general_client.is_closed:
        await _general_client.aclose()
        _general_client = None
