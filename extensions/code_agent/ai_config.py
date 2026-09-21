"""Versioned administrator settings; API keys stay in a private server file."""
from contextvars import ContextVar
import fcntl,json,os,re,tempfile
import httpx
from pathlib import Path
from .store import DomainError

KEYS={'commandcode':'COMMANDCODE_API_KEY','deepseek':'DEEPSEEK_API_KEY','anthropic':'ANTHROPIC_API_KEY','openai':'OPENAI_API_KEY'}
MODELS={'commandcode':'deepseek/deepseek-v4.1-flash','deepseek':'deepseek-flash','anthropic':'claude-sonnet-5','openai':'gpt-4.1-mini'}
_active=ContextVar('ai_configuration',default=None)


def read():
    current=_active.get()
    if current is not None:return current
    path=os.getenv('CODE_AI_SETTINGS_FILE')
    if path and Path(path).exists():
        try:
            value=json.loads(Path(path).read_text())
            if value['provider'] not in KEYS or value['embedding'] not in ('none','local','openai'):raise ValueError()
            return value
        except Exception as exc:raise DomainError('AI 설정 파일을 읽을 수 없습니다.',503) from exc
    provider=os.getenv('CODE_LLM_PROVIDER','openai')
    return {'version':0,'provider':provider,'model':(os.getenv('CODE_LLM_MODEL') or MODELS.get(provider,'')),
            'embedding':os.getenv('CODE_EMBEDDING_PROVIDER','openai'),'keys':{}}


def key(name):return read().get('keys',{}).get(name) or os.getenv(name,'')


def local_status():
    """A configured URL is not evidence that the pinned model can serve requests."""
    url=os.getenv('LOCAL_EMBEDDING_URL','').rstrip('/')
    if not url or not os.getenv('LOCAL_EMBEDDING_TOKEN'):
        return {'local_configured':False,'local_available':False,'local_state':'unconfigured'}
    try:
        from .embeddings import IDENTITY
        response=httpx.get(url+'/health',timeout=2,follow_redirects=False)
        response.raise_for_status();data=response.json()
        if not isinstance(data,dict) or data.get('model')!=IDENTITY:
            return {'local_configured':True,'local_available':False,'local_state':'model_mismatch'}
        if data.get('ready') is True:
            return {'local_configured':True,'local_available':True,'local_state':'ready'}
    except (httpx.HTTPError,ValueError):pass
    return {'local_configured':True,'local_available':False,'local_state':'unavailable'}


def public(config=None,local=None):
    c=config if config is not None else read()
    return {k:c[k] for k in ('version','provider','model','embedding')} | {
        'configured':{p:bool(c.get('keys',{}).get(k) or os.getenv(k)) for p,k in KEYS.items()},
        'models':MODELS} | (local if local is not None else local_status())


def save(body,actor_id):
    if not isinstance(body,dict) or set(body)-{'version','provider','model','embedding','api_key','embedding_api_key'}:
        raise DomainError('AI 설정 항목을 확인해주세요.',422)
    provider=body.get('provider');embedding=body.get('embedding');version=body.get('version')
    if not isinstance(provider,str) or provider not in KEYS or embedding not in ('none','local','openai') or type(version) is not int or version<0:
        raise DomainError('AI 공급자와 검색 방식을 선택해주세요.',422)
    model=body.get('model',MODELS[provider])
    if not isinstance(model,str) or not re.fullmatch(r'[A-Za-z0-9_./:-]{1,160}',model):raise DomainError('모델명을 확인해주세요.',422)
    secret=body.get('api_key','')
    if not isinstance(secret,str) or len(secret)>4096 or any(ch.isspace() for ch in secret):raise DomainError('API 키 형식을 확인해주세요.',422)
    embedding_secret=body.get('embedding_api_key','')
    if not isinstance(embedding_secret,str) or len(embedding_secret)>4096 or any(ch.isspace() for ch in embedding_secret):raise DomainError('임베딩 API 키 형식을 확인해주세요.',422)
    if embedding_secret and (embedding!='openai' or provider=='openai'):
        raise DomainError('임베딩 전용 키는 다른 AI 공급자와 OpenAI 임베딩을 함께 선택할 때 입력해주세요.',422)
    local=local_status()
    if embedding=='local' and not local['local_available']:
        if not local['local_configured']:raise DomainError('로컬 임베딩 서비스가 구성되지 않았습니다. 키워드 검색을 선택하거나 설치 설정에서 로컬 서비스를 준비해주세요.',422)
        raise DomainError('로컬 임베딩 모델이 아직 준비되지 않았습니다. 서비스 시작·모델 로딩 후 다시 시도하거나 키워드 검색을 선택해주세요.',503)
    path=os.getenv('CODE_AI_SETTINGS_FILE')
    if not path:raise DomainError('서버의 AI 설정 저장 경로가 준비되지 않았습니다.',503)
    path=Path(path);path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    with (path.parent/'ai.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        token=_active.set(None)
        try:current=read()
        finally:_active.reset(token)
        if current['version']!=version:raise DomainError('다른 관리자가 설정을 변경했습니다. 새로 불러와주세요.',409)
        keys=dict(current.get('keys',{}))
        if secret:keys[KEYS[provider]]=secret
        if embedding_secret:keys['OPENAI_API_KEY']=embedding_secret
        if not (keys.get(KEYS[provider]) or os.getenv(KEYS[provider])):raise DomainError('선택한 공급자의 API 키를 입력해주세요.',422)
        if embedding=='openai' and not (keys.get('OPENAI_API_KEY') or os.getenv('OPENAI_API_KEY')):
            raise DomainError('OpenAI 임베딩은 OpenAI 키가 필요합니다. 로컬 또는 키워드 검색을 선택할 수 있습니다.',422)
        updated={'version':version+1,'provider':provider,'model':model,'embedding':embedding,'keys':keys,'updated_by':actor_id}
        fd,name=tempfile.mkstemp(dir=path.parent,prefix='.ai-')
        try:
            with os.fdopen(fd,'w') as output:json.dump(updated,output);output.flush();os.fsync(output.fileno())
            os.chmod(name,0o600);os.replace(name,path)
        finally:
            if os.path.exists(name):os.unlink(name)
    return public(updated,local=local)
