"""Lossless transport tests use synthetic values only; no external model calls."""
import copy
import json
import random

import pytest

from code_agent.evidence import FORMAT, decode_evidence, encode_evidence


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def test_sqlalchemy_string_column_names_preserve_live_db_evidence():
    from sqlalchemy.sql.elements import quoted_name
    payload={'catalog':[{quoted_name('code',None):f'QA-{index}',
                         quoted_name('message',None):'등록된 원문',
                         quoted_name('source',None):{'synthetic':True}}
                        for index in range(25)]}
    assert decode_evidence(encode_evidence(payload))==json.loads(json.dumps(payload))


def records(count=25):
    return [
        {'code': f'TEST-{i:04}', 'message': '원문 그대로 30초 이후 ${name}',
         'menu': '', 'trigger': None, 'revision': i, 'status': 'active',
         'source': {'catalog_fields': {'title': '', 'notes': '문의 synthetic@example.test',
                                      'zero': 0, 'false': False, 'numbers': [1, 1.5, -0.0]}},
         'catalog_fields': {}, 'updated_at': 'synthetic', 'id': i}
        for i in range(count)
    ]


def test_many_candidates_preserve_count_order_all_fields_and_input():
    payload = {'question': '조건 비교', 'catalog': records(), 'rule_comparison': []}
    before = copy.deepcopy(payload)
    text = encode_evidence(payload)
    envelope = json.loads(text)
    restored = decode_evidence(text)
    assert envelope['encoding'] == 'columns-rows'
    assert restored == payload == before
    assert len(restored['catalog']) == 25
    assert [row['code'] for row in restored['catalog']] == [row['code'] for row in payload['catalog']]
    assert list(restored['catalog'][0]) == list(payload['catalog'][0])
    assert 'synthetic@example.test' in text  # The caller, not this codec, owns PII masking.
    assert len(text.encode()) < len(compact({'format': FORMAT, 'encoding': 'json', 'data': payload}).encode())


@pytest.mark.parametrize('payload', [None, True, False, 0, -12, -0.0, 1.25, '', '한글\n"문자"', [], {}, [None, '', [], {}]])
def test_json_values_round_trip_without_type_coercion(payload):
    restored = decode_evidence(encode_evidence(payload))
    assert restored == payload
    assert type(restored) is type(payload)
    if type(payload) is float:
        assert compact(restored) == compact(payload)


def test_reserved_keys_and_marker_shaped_original_objects_never_collide():
    marker = {'format': FORMAT, 'encoding': 'columns-rows', 'tables': [{'path': [], 'columns': ['a']}],
              'table_rule': 'At each path in data, row values follow columns in order.', 'data': [['original']]}
    payload = {'format': FORMAT, 'data': marker, 'tables': records(), 'columns': ['x'],
               'rows': [{'path': '/catalog', '$ref': 0, '__table__': {'data': 'original'}}]}
    assert decode_evidence(encode_evidence(payload)) == payload
    assert decode_evidence(encode_evidence(marker)) == marker


def test_root_and_multiple_nested_tables_are_unambiguous():
    for payload in [records(), {'left': records(), 'right': [0, {'nested': records()}]},
                    [{'unequal': True}, {'different': records()}]]:
        text = encode_evidence(payload)
        assert json.loads(text)['encoding'] == 'columns-rows'
        assert decode_evidence(text) == payload


def test_nonuniform_fields_and_different_key_order_are_preserved():
    payload = [{'code': 'TEST-1', 'message': ''}, {'message': None, 'code': 'TEST-2'},
               {'code': 'TEST-3', 'source': {}}]
    restored = decode_evidence(encode_evidence(payload))
    assert restored == payload
    assert [list(row) for row in restored] == [list(row) for row in payload]


def test_random_nested_json_round_trips_and_never_exceeds_plain_envelope():
    rng = random.Random(20260922)
    atoms = [None, True, False, '', '한글', 'columns', 0, -1, 1.25]
    def value(depth):
        choice = rng.randrange(3) if depth else 0
        if choice == 1:
            return [value(depth - 1) for _ in range(rng.randrange(5))]
        if choice == 2:
            return {f'field_{i}': value(depth - 1) for i in range(rng.randrange(5))}
        return rng.choice(atoms)
    for _ in range(150):
        payload = value(4)
        encoded = encode_evidence(payload)
        plain = compact({'format': FORMAT, 'encoding': 'json', 'data': payload})
        assert decode_evidence(encoded) == payload
        assert len(encoded.encode()) <= len(plain.encode())


@pytest.mark.parametrize('payload', [(1, 2), {1: 'not a JSON key'}, float('nan'), float('inf'), {'nested': {1, 2}}])
def test_unsupported_values_rejected_instead_of_silently_losing_type(payload):
    with pytest.raises(ValueError):
        encode_evidence(payload)


@pytest.mark.parametrize('text', ['{}', '{"format":"other","data":0}',
    '{"format":"catalog-evidence/v1","encoding":"json","data":NaN}',
    '{"format":"catalog-evidence/v1","encoding":"json","data":{"same":1,"same":2}}',
    '{"format":"catalog-evidence/v1","encoding":"json","data":0,"extra":1}'])
def test_invalid_or_ambiguous_json_envelopes_fail_closed(text):
    with pytest.raises(ValueError):
        decode_evidence(text)


@pytest.mark.parametrize('mutation', ['duplicate_path', 'ancestor_path', 'missing_path', 'bool_path',
    'duplicate_column', 'short_row', 'not_rows', 'changed_rule', 'extra_descriptor'])
def test_malformed_table_contracts_fail_closed(mutation):
    envelope = json.loads(encode_evidence({'catalog': records()}))
    assert envelope['encoding'] == 'columns-rows'
    table = envelope['tables'][0]
    if mutation == 'duplicate_path': envelope['tables'].append(copy.deepcopy(table))
    elif mutation == 'ancestor_path': envelope['tables'].append({'path': [], 'columns': ['x']})
    elif mutation == 'missing_path': table['path'] = ['missing']
    elif mutation == 'bool_path': table['path'] = [True]
    elif mutation == 'duplicate_column': table['columns'][1] = table['columns'][0]
    elif mutation == 'short_row': envelope['data']['catalog'][0].pop()
    elif mutation == 'not_rows': envelope['data']['catalog'] = {}
    elif mutation == 'changed_rule': envelope['table_rule'] = 'discard blank columns'
    elif mutation == 'extra_descriptor': table['question_answer_mapping'] = {}
    with pytest.raises(ValueError):
        decode_evidence(compact(envelope))
