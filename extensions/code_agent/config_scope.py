"""Keep one model/key/search selection for the lifetime of a background operation."""
import functools
import inspect
from . import ai_config
from .store import DomainError


def pinned_configuration(function):
    if inspect.iscoroutinefunction(function):
        @functools.wraps(function)
        async def wrapped(*args,**kwargs):
            token=ai_config._active.set(ai_config.read())
            try:return await function(*args,**kwargs)
            finally:ai_config._active.reset(token)
    else:
        @functools.wraps(function)
        def wrapped(*args,**kwargs):
            token=ai_config._active.set(ai_config.read())
            try:return function(*args,**kwargs)
            finally:ai_config._active.reset(token)
    return wrapped


def assert_current():
    snapshot=ai_config.read()
    token=ai_config._active.set(None)
    try:current=ai_config.read()
    finally:ai_config._active.reset(token)
    if current['version']!=snapshot['version']:
        raise DomainError('처리 도중 AI 설정이 변경되었습니다. 다시 실행해주세요.',409)
