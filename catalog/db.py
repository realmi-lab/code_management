from __future__ import annotations
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from .models import CATALOG_FIELDS

SCHEMA = '''
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT OR IGNORE INTO meta VALUES ('schema_version','1');
INSERT OR IGNORE INTO meta VALUES ('version:live','0');
INSERT OR IGNORE INTO meta VALUES ('version:demo','0');
CREATE TABLE IF NOT EXISTS codes (
 id TEXT PRIMARY KEY, namespace TEXT NOT NULL CHECK(namespace IN ('live','demo')),
 code TEXT NOT NULL, message TEXT NOT NULL, menu TEXT NOT NULL DEFAULT '',
 trigger_text TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','retired')),
 source_json TEXT NOT NULL DEFAULT '{}', revision INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(namespace,code)
);
CREATE INDEX IF NOT EXISTS idx_codes_scope ON codes(namespace,status);
CREATE TABLE IF NOT EXISTS drafts (
 id TEXT PRIMARY KEY, namespace TEXT NOT NULL, message TEXT NOT NULL,
 menu TEXT NOT NULL DEFAULT '', trigger_text TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
 kind TEXT NOT NULL DEFAULT 'new', target_code TEXT, target_revision INTEGER,
 state TEXT NOT NULL DEFAULT 'draft', registered_code TEXT, revision INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_drafts_scope_state ON drafts(namespace,state);
CREATE INDEX IF NOT EXISTS idx_drafts_scope_created ON drafts(namespace,created_at DESC);
CREATE TABLE IF NOT EXISTS imports (
 id TEXT PRIMARY KEY, namespace TEXT NOT NULL, filename TEXT NOT NULL,
 checksum TEXT NOT NULL, payload TEXT NOT NULL, catalog_version INTEGER NOT NULL,
 consumed INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
 id INTEGER PRIMARY KEY AUTOINCREMENT, namespace TEXT NOT NULL, action TEXT NOT NULL,
 entity TEXT NOT NULL, before_json TEXT, after_json TEXT, reason TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_scope_id ON audit(namespace,id DESC);
CREATE TABLE IF NOT EXISTS sequences (
 namespace TEXT NOT NULL, prefix TEXT NOT NULL, next_number INTEGER NOT NULL,
 PRIMARY KEY(namespace,prefix)
);
CREATE TABLE IF NOT EXISTS embeddings (
 code_id TEXT NOT NULL REFERENCES codes(id) ON DELETE CASCADE,
 model TEXT NOT NULL, fingerprint TEXT NOT NULL, vector TEXT NOT NULL,
 PRIMARY KEY(code_id,model)
);
'''

def now():
    return datetime.now(timezone.utc).isoformat()

def uid():
    return str(uuid.uuid4())

def dumps(v):
    return json.dumps(v, ensure_ascii=False, separators=(',',':'))

class DB:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            con.executescript(SCHEMA)

    @contextmanager
    def connect(self, write=False):
        con = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA foreign_keys=ON')
        con.execute('PRAGMA busy_timeout=15000')
        try:
            if write:
                con.execute('BEGIN IMMEDIATE')
            yield con
            if write:
                con.commit()
        except Exception:
            if write:
                con.rollback()
            raise
        finally:
            con.close()

    def version(self, namespace, con=None):
        if con is None:
            with self.connect() as c:
                return self.version(namespace,c)
        return int(con.execute('SELECT value FROM meta WHERE key=?',('version:'+namespace,)).fetchone()[0])

    def bump(self, con, namespace):
        con.execute('UPDATE meta SET value=CAST(value AS INTEGER)+1 WHERE key=?',('version:'+namespace,))

    def all_codes(self, namespace, include_retired=True, con=None):
        if con is None:
            with self.connect() as c:
                return self.all_codes(namespace, include_retired, c)
        sql = 'SELECT * FROM codes WHERE namespace=?'
        if not include_retired:
            sql += " AND status='active'"
        return [decode_code(x) for x in con.execute(sql+' ORDER BY code',(namespace,))]

    def count_codes(self, namespace, include_retired=True, con=None):
        if con is None:
            with self.connect() as c:
                return self.count_codes(namespace,include_retired,c)
        sql='SELECT COUNT(*) FROM codes WHERE namespace=?'
        if not include_retired: sql+=" AND status='active'"
        return con.execute(sql,(namespace,)).fetchone()[0]

    def catalog_stats(self, namespace, con=None):
        if con is None:
            with self.connect() as c:
                return self.catalog_stats(namespace,c)
        row=con.execute("""SELECT COUNT(*) AS total,
            COALESCE(SUM(status='active'),0) AS active,
            COALESCE(SUM(status='retired'),0) AS retired,
            (SELECT COUNT(*) FROM drafts WHERE namespace=? AND state!='registered') AS drafts
            FROM codes WHERE namespace=?""",(namespace,namespace)).fetchone()
        return dict(row)

    def page_codes(self, namespace, q='', status='all', offset=0, limit=50):
        # Filter and page before decoding source JSON. Python lower preserves the
        # Unicode substring behavior of the original in-memory implementation.
        with self.connect() as con:
            con.execute('BEGIN')
            where='namespace=?';params=[namespace]
            if status!='all': where+=' AND status=?';params.append(status)
            if q:
                con.create_function('unicode_lower',1,str.lower,deterministic=True)
                metadata=" || ' ' || ".join(
                    "COALESCE(CAST(json_extract(CASE WHEN json_valid(source_json) THEN source_json ELSE '{}' END, "
                    "'$.catalog_fields."+field+"') AS TEXT),'')" for field in CATALOG_FIELDS)
                where+=" AND instr(unicode_lower(code || ' ' || message || ' ' || menu || ' ' || trigger_text || ' ' || "+metadata+"),?)>0"
                params.append(q.lower())
            total=con.execute('SELECT COUNT(*) FROM codes WHERE '+where,params).fetchone()[0]
            rows=con.execute('SELECT * FROM codes WHERE '+where+' ORDER BY code LIMIT ? OFFSET ?',
                             [*params,limit,offset]).fetchall()
            return {'items':[decode_code(row) for row in rows],'total':total,'offset':offset,
                    'limit':limit,'catalog_version':self.version(namespace,con)}

    def get_code(self, namespace, code, con=None):
        if con is None:
            with self.connect() as c:
                return self.get_code(namespace,code,c)
        row = con.execute('SELECT * FROM codes WHERE namespace=? AND code=?',(namespace,code)).fetchone()
        return decode_code(row) if row else None

    def insert_code(self, con, namespace, row, source):
        ident, stamp = uid(), now()
        source=dict(source or {})
        stored=source.get('catalog_fields',{})
        stored=stored if isinstance(stored,dict) else {}
        # Import rows and direct inserts share one persisted metadata contract.
        source['catalog_fields']={field:row.get(field,stored.get(field,'')) for field in CATALOG_FIELDS}
        con.execute('''INSERT INTO codes
          (id,namespace,code,message,menu,trigger_text,notes,status,source_json,created_at,updated_at)
          VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
          (ident,namespace,row['code'],row['message'],row.get('menu',''),row.get('trigger',''),
           row.get('notes',''),row.get('status','active'),dumps(source),stamp,stamp))
        self.audit(con,namespace,'code.imported',row['code'],None,row,'원문 등록')
        return ident

    def audit(self, con, ns, action, entity, before, after, reason=''):
        con.execute('''INSERT INTO audit(namespace,action,entity,before_json,after_json,reason,created_at)
            VALUES(?,?,?,?,?,?,?)''',(ns,action,entity,dumps(before) if before is not None else None,
             dumps(after) if after is not None else None,reason,now()))


def decode_code(row):
    d = dict(row)
    d['trigger'] = d.pop('trigger_text')
    d['source'] = json.loads(d.pop('source_json'))
    fields=d['source'].get('catalog_fields',{}) if isinstance(d['source'],dict) else {}
    fields=fields if isinstance(fields,dict) else {}
    d.update({field:fields.get(field,'') for field in CATALOG_FIELDS})
    return d

def decode_draft(row):
    d = dict(row)
    d['trigger'] = d.pop('trigger_text')
    return d
