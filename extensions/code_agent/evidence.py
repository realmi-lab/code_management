"""Lossless, versioned JSON evidence encoding; never filters catalogue facts.

Only arrays of objects with identical ordered keys may become column/row tables.
Table locations live outside the user's data, so reserved-looking field names
remain ordinary evidence. The shorter UTF-8 representation wins; actual model
token savings must be measured from provider usage, not inferred from bytes.
"""
from __future__ import annotations

import json
import math
from typing import Any

FORMAT = 'catalog-evidence/v1'


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _size(value: Any) -> int:
    return len(_json(value).encode('utf-8'))


def _validate_json(value: Any) -> None:
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is list:
        for item in value:
            _validate_json(item)
        return
    # SQLAlchemy PostgreSQL row keys can be quoted_name, a str subclass.
    # JSON has string keys; preserve their text just as json.dumps does.
    if type(value) is dict and all(isinstance(key,str) for key in value):
        for item in value.values():
            _validate_json(item)
        return
    raise ValueError('Evidence must contain only JSON values and string object keys')


def _pack(value: Any, path: list) -> tuple[Any, list[dict]]:
    if type(value) is list:
        if len(value) >= 2 and all(type(row) is dict for row in value):
            columns = list(value[0])
            if columns and all(list(row) == columns for row in value):
                rows = [[row[column] for column in columns] for row in value]
                table = {'path': path, 'columns': columns}
                # A selected table is atomic: nested values remain exact JSON.
                if _size(rows) + _size(table) + 2 < _size(value):
                    return rows, [table]
        result, tables = [], []
        for index, item in enumerate(value):
            packed, nested = _pack(item, path + [index])
            result.append(packed)
            tables.extend(nested)
        return result, tables
    if type(value) is dict:
        result, tables = {}, []
        for key, item in value.items():
            packed, nested = _pack(item, path + [key])
            result[key] = packed
            tables.extend(nested)
        return result, tables
    return value, []


def encode_evidence(payload: Any) -> str:
    """Encode every field/value in order without mutating or redacting payload."""
    _validate_json(payload)
    plain = _json({'format': FORMAT, 'encoding': 'json', 'data': payload})
    data, tables = _pack(payload, [])
    if not tables:
        return plain
    tabular = _json({
        'format': FORMAT,
        'encoding': 'columns-rows',
        'table_rule': 'At each path in data, row values follow columns in order.',
        'tables': tables,
        'data': data,
    })
    return tabular if len(tabular.encode('utf-8')) < len(plain.encode('utf-8')) else plain


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON object key')
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError('Non-finite JSON number')


def _locate(data: Any, path: list) -> Any:
    current = data
    for part in path:
        if type(part) is str and type(current) is dict and part in current:
            current = current[part]
        elif type(part) is int and type(current) is list and 0 <= part < len(current):
            current = current[part]
        else:
            raise ValueError('Invalid evidence table path')
    return current


def decode_evidence(text: str) -> Any:
    """Restore encoded evidence; malformed or ambiguous envelopes are rejected."""
    envelope = json.loads(text, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    _validate_json(envelope)
    if type(envelope) is not dict or envelope.get('format') != FORMAT:
        raise ValueError('Unsupported evidence format')
    encoding = envelope.get('encoding')
    if encoding == 'json':
        if set(envelope) != {'format', 'encoding', 'data'}:
            raise ValueError('Invalid JSON evidence envelope')
        return envelope['data']
    if encoding != 'columns-rows' or set(envelope) != {'format', 'encoding', 'table_rule', 'tables', 'data'}:
        raise ValueError('Invalid table evidence envelope')
    if envelope['table_rule'] != 'At each path in data, row values follow columns in order.':
        raise ValueError('Unsupported evidence table rule')
    tables = envelope['tables']
    if type(tables) is not list or not tables:
        raise ValueError('Evidence tables must be a nonempty list')
    paths = []
    for table in tables:
        if type(table) is not dict or set(table) != {'path', 'columns'}:
            raise ValueError('Invalid evidence table descriptor')
        path, columns = table['path'], table['columns']
        if type(path) is not list or any(type(p) not in (str, int) or (type(p) is int and p < 0) for p in path):
            raise ValueError('Invalid evidence table path')
        if type(columns) is not list or not columns or any(type(c) is not str for c in columns) or len(set(columns)) != len(columns):
            raise ValueError('Invalid evidence table columns')
        if any(path[:len(other)] == other or other[:len(path)] == path for other in paths):
            raise ValueError('Overlapping evidence table paths')
        paths.append(path)
    data = envelope['data']
    for table in tables:
        path, columns = table['path'], table['columns']
        rows = _locate(data, path)
        if type(rows) is not list or any(type(row) is not list or len(row) != len(columns) for row in rows):
            raise ValueError('Invalid evidence table rows')
        restored = [dict(zip(columns, row)) for row in rows]
        if not path:
            data = restored
        else:
            parent = _locate(data, path[:-1])
            parent[path[-1]] = restored
    return data
