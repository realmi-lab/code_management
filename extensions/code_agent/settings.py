"""Keep saved RAG preferences independent of temporary provider prerequisites."""
import asyncio
from weakref import WeakKeyDictionary
from pydantic import ValidationError
from .provider import apply_model_settings, raw_model_settings


_settings_api_locks = WeakKeyDictionary()


def settings_api_lock():
    """Protect the upstream singleton's request-owned DB session assignment."""
    loop = asyncio.get_running_loop()
    lock = _settings_api_locks.get(loop)
    if lock is None:
        lock = asyncio.Lock()
        _settings_api_locks[loop] = lock
    return lock


def decode_cached_preferences(cached):
    """Discard obsolete or corrupt cache values without changing shared input."""
    if not isinstance(cached, dict) or cached.get('_catalog_raw_preferences') is not True:
        return None
    from app.config import RAGSettings
    values = {key: value for key, value in cached.items() if key != '_catalog_raw_preferences'}
    try:
        with raw_model_settings():
            return RAGSettings(**values)
    except (ValidationError, TypeError, ValueError):
        return None


class PreferenceSettingsMixin:
    def _preference_lock(self):
        # Serialize this service's cache fills and read-modify-write updates.
        # The lock is created lazily for upstream constructor compatibility.
        if not hasattr(self, '_preferences_lock'):
            self._preferences_lock = asyncio.Lock()
        return self._preferences_lock

    async def _raw_preferences(self):
        async with self._preference_lock():
            return await self._read_raw_preferences()

    async def _read_raw_preferences(self):
        # The upstream cache and database contain user choices, never runtime
        # keyword-only constraints. Each caller receives its own effective copy.
        with raw_model_settings():
            return await super().get_settings()

    async def get_settings(self):
        settings = (await self._raw_preferences()).model_copy(deep=True)
        apply_model_settings(settings)
        return settings

    async def get_preferences(self):
        raw = await self._raw_preferences()
        settings = raw.model_copy(deep=True)
        apply_model_settings(settings)
        for field in ('search_mode', 'hyde_enabled', 'multi_query_enabled', 'chunking_strategy'):
            setattr(settings, field, getattr(raw, field))
        return settings

    async def update_settings(self, updates):
        async with self._preference_lock():
            return await self._update_preferences(updates)

    async def _update_preferences(self, updates):
        from app.config import RAGSettings
        current = await self._read_raw_preferences()
        data = current.model_dump()
        data.update({key: value for key, value in updates.items() if value is not None})
        with raw_model_settings():
            updated = RAGSettings(**data)
        await self._save_to_db(updated)
        self._local_cache = None
        if self._cache_svc:
            await self._cache_svc.invalidate_settings()
            await self._cache_svc.invalidate_search()
        # Match GET /settings: editing forms display the saved preferences.
        result = updated.model_copy(deep=True)
        apply_model_settings(result)
        for field in ('search_mode', 'hyde_enabled', 'multi_query_enabled', 'chunking_strategy'):
            setattr(result, field, getattr(updated, field))
        return result
