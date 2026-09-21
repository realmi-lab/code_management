"""Run after upstream alembic; only creates cm_* domain tables."""
from app.config import get_settings
from .store import Store
if __name__=='__main__':
    store=Store(get_settings().database_url)
    try: store.initialize();print('Code catalog schema ready.')
    finally: store.engine.dispose()
