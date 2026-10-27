"""Generate tiny artificial fixtures, verify tools, and clean temporary files.

All numbers below are hand-written examples. No enterprise data is read.
Use --out NEW_DIRECTORY only when you explicitly want to retain demo reports.
"""
import argparse
import copy
import csv
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import uuid

sys.dont_write_bytecode = True
from rrs_audit import audit, sha256
from experience_store import content_hash, promote, retrieve, write_new


def make_inputs(root):
    rows = {
        'daily': [
            dict(run_id='demo-run', date='2020-01-01', request=6, sales=5, lost=1,
                 closing_E=10, closing_N=2, factory_receipt=0, warehouse_receipt=0,
                 warehouse_out=0, sales_contribution=50, warehouse_transport_cost=10, net_contribution=40),
            dict(run_id='demo-run', date='2020-01-02', request=6, sales=4, lost=2,
                 closing_E=7, closing_N=1, factory_receipt=0, warehouse_receipt=0,
                 warehouse_out=0, sales_contribution=40, warehouse_transport_cost=0, net_contribution=40),
        ],
        'trips': [dict(run_id='demo-run', date='2020-01-01', trip_id='demo-trip',
                       source='warehouse-a', destination='warehouse-b', available='2020-01-02',
                       quantity=2, SKU_count=2, quantity_vector='[1,1]', weight_kg=20, volume_m3=0.2, cost_CNY=7)],
        'forecast': [dict(node='demo-node', date='2020-01-01', actual=10, selected=12, lower=8, upper=16),
                     dict(node='demo-node', date='2020-01-02', actual=20, selected=18, lower=15, upper=24)],
        'emergency': [dict(panel='SYNTHETIC', arm='demo', J=10, emergency=0, local=-10,
                          transport=20, gap=5, served=5, satisfaction=1, seconds=1, valid='true')],
        'paired': [dict(run_id='demo-candidate', baseline_run_id='demo-baseline', window='DEMO',
                       baseline='demo', delta_net_CNY=2000, delta_net_wanyuan=0.2)],
    }
    (root / 'data').mkdir()
    bindings = {'schema_version': 1, 'vehicle': {'kg': 100, 'm3': 1.5}, 'datasets': {}}
    for key, values in rows.items():
        path = root / 'data' / (key + '.csv')
        with path.open('x', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(values[0]))
            writer.writeheader()
            writer.writerows(values)
        bindings['datasets'][key] = {'path': 'data/' + key + '.csv', 'sha256': sha256(path),
                                     'scope': 'synthetic_development'}
    write_new(root / 'bindings.json', bindings)
    return bindings


def make_experiences(root, report):
    kb = root / 'knowledge_base'
    write_new(kb / 'evidence' / 'audit.json', report)
    evidence = {'path': 'evidence/audit.json', 'sha256': sha256(kb / 'evidence/audit.json'),
                'detail': 'Checks on hand-written synthetic fixtures; no business validation.'}
    expected = {}
    for module, dataset in [('routine', 'daily'), ('forecast', 'forecast'), ('emergency', 'emergency')]:
        item = next(x for x in report['checks'] if x['dataset'] == dataset)
        entry = dict(schema_version=1, id='demo-' + module + '-review', version='1.0.0',
                     title='Synthetic ' + module + ' review', module=module, kind='procedure', status='draft',
                     source_scope='synthetic_development', target_scopes=['synthetic_development'],
                     available_at='2020-01-03T00:00:00+00:00', applicability={'profile': 'toy-v1'},
                     triggers=[{'field': 'task', 'op': 'eq', 'value': 'result_review'}],
                     evidence=[evidence], steps=['Review the deterministic audit and its limitations.'],
                     constraints=['Synthetic fixtures only; no production actions.'],
                     not_applicable=['Real business operations or a different configuration.'], validation=None)
        validation = dict(schema_version=1, entry_id=entry['id'], kind=entry['kind'],
                          entry_content_sha256=content_hash(entry), result='pass', reviewer='synthetic-demo-check',
                          validated_at='2020-01-03T00:00:00+00:00', source_scope=entry['source_scope'],
                          target_scopes=entry['target_scopes'], applicability=entry['applicability'],
                          evidence_sha256=[evidence['sha256']], method='deterministic_audit',
                          checks=[{'name': 'artificial_fixture_consistency',
                                   'passed': item['status'] == 'PASS' and item['binding_hash_matches'],
                                   'detail': 'This is a generated demo validation, not an independent field review.'}])
        validation_path = kb / 'validation' / (module + '.json')
        write_new(validation_path, validation)
        validated = promote(entry, validation_path, kb)
        write_new(kb / 'entries' / (entry['id'] + '.json'), validated)
        expected[module] = entry['id']
        if module == 'routine':
            draft = copy.deepcopy(entry)
            draft['id'] = 'demo-unvalidated-draft'
            write_new(kb / 'entries' / 'draft.json', draft)
    return kb, expected


def evaluate(root):
    bindings = make_inputs(root)
    report = audit(root, bindings)
    write_new(root / 'audit.json', report)
    if not report['checks'] or any(x['status'] != 'PASS' or not x.get('binding_hash_matches') for x in report['checks']):
        raise ValueError('Synthetic fixture audit failed')
    kb, expected = make_experiences(root, report)
    hits = {}
    for module, entry_id in expected.items():
        context = dict(module=module, source_scope='synthetic_development', profile='toy-v1',
                       knowledge_cutoff='2020-01-04T00:00:00+00:00', task='result_review', query='review')
        write_new(kb / 'contexts' / (module + '.json'), context)
        result = retrieve(kb, context)
        hits[module] = [x['id'] for x in result['matches']]
        if hits[module] != [entry_id] or result['executable']:
            raise ValueError('Synthetic retrieval did not match its validated procedure')
        write_new(root / ('retrieval-' + module + '.json'), result)
    context = dict(module='routine', source_scope='enterprise_execution', profile='toy-v1',
                   knowledge_cutoff='2020-01-04T00:00:00+00:00', task='result_review', query='review')
    cross = retrieve(kb, context)
    context['source_scope'] = 'synthetic_development'
    context['knowledge_cutoff'] = '2020-01-01T00:00:00+00:00'
    early = retrieve(kb, context)
    if cross['matches'] or early['matches']:
        raise ValueError('Source or historical cutoff gate failed')
    write_new(root / 'cross-source-blocked.json', cross)
    write_new(root / 'historical-cutoff-blocked.json', early)
    summary = dict(schema_version=1, mode='synthetic_method_demo', status='PASS',
                   data_source='hand_written_synthetic_examples',
                   dataset_rows={x['dataset']: x['rows'] for x in report['checks']},
                   retrieval_hits=hits, cross_source_blocked=True, historical_cutoff_blocked=True,
                   llm_status='not_configured', production_state_mutated=False,
                   limitations=['No enterprise data', 'No solver rerun', 'No model request', 'No geometric certificate'])
    write_new(root / 'summary.json', summary)
    return summary


def run_demo(out=None):
    temporary = out is None
    base = Path(os.environ.get('RRS_DEMO_TMP_DIR', tempfile.gettempdir())).resolve()
    if temporary:
        base.mkdir(parents=True, exist_ok=True)
        root = base / ('rrs-method-demo-' + uuid.uuid4().hex)
    else:
        root = Path(out).resolve()
    root.mkdir(parents=True, exist_ok=False)
    try:
        summary = evaluate(root)
        return {**summary, 'reports_saved': not temporary}
    finally:
        if temporary:
            target = root.resolve()
            if target == base or not target.is_relative_to(base) or not target.name.startswith('rrs-method-demo-'):
                raise RuntimeError('Refusing cleanup outside generated demo directory')
            shutil.rmtree(target)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, help='Optional new directory for synthetic reports; omitted means automatic cleanup')
    a = p.parse_args()
    try:
        print(json.dumps(run_demo(a.out), ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({'status': 'FAIL', 'error': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
