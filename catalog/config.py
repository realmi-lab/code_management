from __future__ import annotations
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent

@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv('DATA_DIR', str(ROOT / 'data'))))
    access_token: str = field(default_factory=lambda: os.getenv('ACCESS_TOKEN', ''))
    admin_password: str = field(default_factory=lambda: os.getenv('ADMIN_PASSWORD', ''))
    catalog_label: str = field(default_factory=lambda: os.getenv('CATALOG_LABEL', ''))
    catalog_notice: str = field(default_factory=lambda: os.getenv('CATALOG_NOTICE', ''))
    authority: str = field(default_factory=lambda: os.getenv('CATALOG_AUTHORITY', 'excel'))
    ai_enabled: bool = field(default_factory=lambda: os.getenv('AI_ENABLED', 'false').lower() == 'true')
    ai_base_url: str = field(default_factory=lambda: os.getenv('AI_BASE_URL', 'http://host.docker.internal:1234/v1'))
    ai_key: str = field(default_factory=lambda: os.getenv('AI_API_KEY', ''))
    ai_chat_model: str = field(default_factory=lambda: os.getenv('AI_CHAT_MODEL', ''))
    ai_embedding_model: str = field(default_factory=lambda: os.getenv('AI_EMBEDDING_MODEL', ''))
    ai_allow_external: bool = field(default_factory=lambda: os.getenv('AI_ALLOW_EXTERNAL', 'false').lower() == 'true')
    ai_provider: str = field(default_factory=lambda: os.getenv('AI_PROVIDER', 'openai-compatible'))
    command_code_bin: str = field(default_factory=lambda: os.getenv('COMMAND_CODE_BIN', 'cmd'))
    claude_code_bin: str = field(default_factory=lambda: os.getenv('CLAUDE_CODE_BIN', 'claude'))
    ai_reasoning_effort: str = field(default_factory=lambda: os.getenv('AI_REASONING_EFFORT', 'low'))
    ai_timeout: float = field(default_factory=lambda: float(os.getenv('AI_TIMEOUT_SECONDS', '90')))
    max_upload: int = 8 * 1024 * 1024
    max_rows: int = 10000
    code_rules: dict = field(default_factory=lambda: json.loads(os.getenv('CODE_RULES_JSON', '{}')))
    allowed_hosts: list[str] = field(default_factory=lambda: os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1,::1,testserver,host.docker.internal').split(','))

    def __post_init__(self):
        if self.authority not in ('excel', 'system'):
            raise ValueError('CATALOG_AUTHORITY must be excel or system')
        self.data_dir = Path(self.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if self.ai_provider not in ('openai-compatible', 'command-code', 'claude-code'):
            raise ValueError('Unsupported AI_PROVIDER')
        if self.ai_reasoning_effort not in ('low', 'high', 'max'):
            raise ValueError('Invalid AI_REASONING_EFFORT')
        if not 1 <= self.ai_timeout <= 600:
            raise ValueError('AI_TIMEOUT_SECONDS must be between 1 and 600')
        if self.ai_enabled and self.ai_provider in ('command-code', 'claude-code'):
            if not self.ai_allow_external:
                raise ValueError('CLI AI transports require AI_ALLOW_EXTERNAL=true')
            if self.ai_embedding_model:
                raise ValueError('CLI AI transports do not support embeddings')
        if self.ai_enabled and self.ai_provider == 'claude-code' and not self.ai_key:
            raise ValueError('Claude Code requires AI_API_KEY')
        if self.ai_enabled and self.ai_provider == 'openai-compatible':
            u = urlparse(self.ai_base_url)
            if u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password or u.query or u.fragment:
                raise ValueError('AI_BASE_URL must be an http(s) API base URL without credentials, query or fragment')
            local = u.hostname in ('localhost', '127.0.0.1', '::1', 'host.docker.internal')
            if not local and not self.ai_allow_external:
                raise ValueError('External AI endpoint requires explicit AI_ALLOW_EXTERNAL=true consent')
            if not local and u.scheme != 'https':
                raise ValueError('External AI connections must use HTTPS')
        for prefix, rule in self.code_rules.items():
            import re
            if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,15}', prefix):
                raise ValueError('Invalid code prefix')
            if not isinstance(rule, dict) or not isinstance(rule.get('start'), int) or not isinstance(rule.get('width'), int):
                raise ValueError('Code rule requires integer start and width')
            if not 1 <= rule['start'] <= 999999999999 or not 1 <= rule['width'] <= 12:
                raise ValueError('Invalid code numbering limits')
