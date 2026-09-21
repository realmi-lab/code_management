"""Production entrypoint: adds a router to the original app, not another login/app."""
from contextlib import asynccontextmanager
import os
from pathlib import Path
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from app.main import app
from app.dependencies import get_current_user
from app.config import get_settings
from .store import Store,DomainError,SampleStore
from .gateway import UrstoryGateway
from .api import create_router

store=Store(get_settings().database_url)
gateway=UrstoryGateway(store)
sample_gateway=UrstoryGateway(SampleStore(store))

def enqueue():
    from .worker import index_catalog
    index_catalog.delay()

def enqueue_sample():
    from .worker import index_catalog
    index_catalog.delay('demo')

app.include_router(create_router(store,gateway,get_current_user,enqueue,sample_gateway=sample_gateway,enqueue_sample=enqueue_sample))
app.mount('/api/code-catalog/ui',StaticFiles(directory=Path(__file__).parent/'static',html=True),name='code-catalog-ui')
@app.exception_handler(DomainError)
async def domain_error(request,exc): return JSONResponse(status_code=exc.status,content={'detail':exc.message})

_original_lifespan=app.router.lifespan_context
@asynccontextmanager
async def lifespan(application):
    async with _original_lifespan(application):
        gateway.monitor=getattr(application.state,'langfuse_monitor',None)
        sample_gateway.monitor=gateway.monitor
        # Schema creation is performed by the migration service, not by request workers.
        store.status()
        yield
        store.engine.dispose()
app.router.lifespan_context=lifespan

@app.middleware("http")
async def workspace_headers(request,call_next):
    if os.getenv('CODE_AUTH_MODE','jwt')=='local' and request.method not in ('GET','HEAD','OPTIONS'):
        origin=request.headers.get('origin')
        allowed=set(get_settings().cors_origins.split(',')) if isinstance(get_settings().cors_origins,str) else set(get_settings().cors_origins)
        if origin and origin not in allowed:
            return JSONResponse(status_code=403,content={'detail':'이 앱의 화면에서 요청해주세요.'})
    from . import ai_config
    token=ai_config._active.set(ai_config.read())
    try:response=await call_next(request)
    finally:ai_config._active.reset(token)
    if request.url.path.startswith('/api/code-catalog/ui/'):
        # Narrow, same-origin embedding only; other upstream routes keep DENY.
        response.headers['X-Frame-Options']='SAMEORIGIN'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'self'; base-uri 'none'; object-src 'none'"
    if request.url.path.startswith('/api/code-catalog/'):
        response.headers['Cache-Control']='no-store'
    return response
