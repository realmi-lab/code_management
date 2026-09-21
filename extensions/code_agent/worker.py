import asyncio
from app.worker import celery_app

@celery_app.task(name='code_catalog.index',soft_time_limit=1800,time_limit=1900)
def index_catalog(namespace="production"):
    from .indexer import rebuild
    return asyncio.run(rebuild(namespace))

@celery_app.task(name='code_catalog.reconcile')
def reconcile():
    from app.config import get_settings
    from .store import Store,SampleStore
    store=Store(get_settings().database_url)
    try:
        s=store.status()
        sample=SampleStore(store).status()
        if sample['version']>sample['indexed_version'] and not sample['index_error']:index_catalog.delay('demo')
        # Pause after an error instead of repeatedly consuming paid embeddings.
        if s['version']>s['indexed_version'] and not s['index_error']: index_catalog.delay()
    finally: store.engine.dispose()

celery_app.conf.beat_schedule={**celery_app.conf.beat_schedule,'catalog-reconcile':{'task':'code_catalog.reconcile','schedule':300.0}}
