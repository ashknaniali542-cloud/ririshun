"""Read-only RRS result auditing. Standard library only; never invokes solvers."""
import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def number(value):
    x = float(value)
    if not math.isfinite(x):
        raise ValueError('non-finite number')
    return x


def close(a, b, tol=1e-5):
    return abs(a - b) <= tol


def daily_checks(rows):
    problems, runs, seen = [], defaultdict(list), set()
    keys = ('request', 'sales', 'lost', 'closing_E', 'closing_N',
            'factory_receipt', 'warehouse_receipt', 'warehouse_out',
            'sales_contribution', 'warehouse_transport_cost', 'net_contribution')
    for line, row in enumerate(rows, 2):
        try:
            d = {k: number(row[k]) for k in keys}
            day = date.fromisoformat(row['date'])
            if not row['run_id']:
                raise ValueError('empty run_id')
            key = (row['run_id'], day)
            if key in seen:
                problems.append({'line': line, 'check': 'duplicate_run_date'})
            seen.add(key)
            if any(d[k] < 0 for k in keys if k != 'net_contribution'):
                problems.append({'line': line, 'check': 'negative_quantity_or_gross_cost'})
            if any(not d[k].is_integer() for k in keys[:8]):
                problems.append({'line': line, 'check': 'noninteger_units'})
            if not close(d['request'], d['sales'] + d['lost']):
                problems.append({'line': line, 'check': 'request_sales_lost'})
            if not close(d['net_contribution'], d['sales_contribution'] - d['warehouse_transport_cost']):
                problems.append({'line': line, 'check': 'net_contribution_balance'})
            runs[row['run_id']].append((day, line, d))
        except (ValueError, KeyError, TypeError) as exc:
            problems.append({'line': line, 'check': 'invalid_row', 'detail': str(exc)})
    transitions, gaps, summaries = 0, 0, []
    for run_id, entries in sorted(runs.items()):
        entries.sort(key=lambda x: x[0])
        for (prev_day, _, prev), (day, line, cur) in zip(entries, entries[1:]):
            if (day - prev_day).days != 1:
                gaps += 1
                continue
            transitions += 1
            expected = prev['closing_E'] + prev['closing_N'] + cur['factory_receipt'] + cur['warehouse_receipt'] - cur['warehouse_out'] - cur['sales']
            if not close(cur['closing_E'] + cur['closing_N'], expected):
                problems.append({'line': line, 'check': 'network_inventory_balance'})
        request = sum(d['request'] for _, _, d in entries)
        summaries.append({'run_id': run_id, 'days': len(entries),
                          'first_day': str(entries[0][0]), 'last_day': str(entries[-1][0]),
                          'net_contribution_CNY': sum(d['net_contribution'] for _, _, d in entries),
                          'fill_rate': sum(d['sales'] for _, _, d in entries) / request if request else None})
    return problems, {'runs': summaries, 'consecutive_transitions_checked': transitions,
                      'date_gaps_not_checked': gaps,
                      'boundary': 'Network totals only; no first-day opening inventory or warehouse/SKU proof.'}


def trip_checks(rows, max_kg, max_m3):
    problems, seen, weights, volumes = [], set(), [], []
    for line, row in enumerate(rows, 2):
        try:
            qty, kg, volume, fee = (number(row[k]) for k in ('quantity', 'weight_kg', 'volume_m3', 'cost_CNY'))
            key = tuple(row[k] for k in ('run_id', 'date', 'trip_id'))
            if any(not v for v in key):
                raise ValueError('empty trip identity')
            if key in seen:
                problems.append({'line': line, 'check': 'duplicate_trip'})
            seen.add(key)
            if qty <= 0 or not qty.is_integer() or kg <= 0 or volume <= 0 or fee < 0:
                problems.append({'line': line, 'check': 'invalid_quantity_or_resource'})
            if kg > max_kg + 1e-5 or volume > max_m3 + 1e-5:
                problems.append({'line': line, 'check': 'vehicle_capacity'})
            if not row['source'] or not row['destination'] or row['source'] == row['destination']:
                problems.append({'line': line, 'check': 'invalid_route'})
            if date.fromisoformat(row['available']) <= date.fromisoformat(row['date']):
                problems.append({'line': line, 'check': 'nonpositive_transit_days'})
            vector = json.loads(row['quantity_vector'])
            if not isinstance(vector, list) or not vector or any(type(v) is not int or v < 0 for v in vector):
                raise ValueError('invalid quantity vector')
            if sum(vector) != qty or sum(v > 0 for v in vector) != number(row['SKU_count']):
                problems.append({'line': line, 'check': 'quantity_vector_balance'})
            weights.append(kg)
            volumes.append(volume)
        except (ValueError, KeyError, TypeError) as exc:
            problems.append({'line': line, 'check': 'invalid_row', 'detail': str(exc)})
    return problems, {'max_weight_kg': max(weights, default=None), 'max_volume_m3': max(volumes, default=None),
                      'limits': {'kg': max_kg, 'm3': max_m3},
                      'geometry_status': 'NOT_CHECKED', 'actual_execution_status': 'NOT_CHECKED'}


def forecast_checks(rows):
    problems, actual, predicted, covered, widths, seen = [], [], [], [], [], set()
    for line, row in enumerate(rows, 2):
        try:
            a, p, low, high = (number(row[k]) for k in ('actual', 'selected', 'lower', 'upper'))
            key = (row['node'], date.fromisoformat(row['date']))
            if not row['node'] or key in seen:
                problems.append({'line': line, 'check': 'invalid_or_duplicate_node_date'})
            seen.add(key)
            if min(a, p) < 0 or low > high:
                problems.append({'line': line, 'check': 'invalid_forecast_range'})
            actual.append(a); predicted.append(p); covered.append(low <= a <= high); widths.append(high - low)
        except (ValueError, KeyError, TypeError) as exc:
            problems.append({'line': line, 'check': 'invalid_row', 'detail': str(exc)})
    n = len(actual)
    errors = [p-a for p, a in zip(predicted, actual)]
    return problems, {'unit': 'completed_business_records_not_SKU_pieces', 'observations': n,
                      'MAE': statistics.mean(map(abs, errors)) if n else None,
                      'RMSE': math.sqrt(statistics.mean(e*e for e in errors)) if n else None,
                      'WAPE_pct': 100*sum(map(abs, errors))/sum(actual) if sum(actual) else None,
                      'bias': statistics.mean(errors) if n else None,
                      'interval_coverage': statistics.mean(covered) if n else None,
                      'mean_interval_width': statistics.mean(widths) if n else None,
                      'live_information_availability': 'NOT_CHECKED', 'missing_rows': 'not zero-filled'}


def emergency_checks(rows):
    problems, groups = [], defaultdict(list)
    for line, row in enumerate(rows, 2):
        try:
            vals = {k: number(row[k]) for k in ('J', 'emergency', 'local', 'transport', 'gap', 'served', 'satisfaction', 'seconds')}
            if not close(vals['J'], vals['emergency'] + vals['local'] + vals['transport']):
                problems.append({'line': line, 'check': 'objective_decomposition'})
            if min(vals['gap'], vals['served'], vals['transport'], vals['emergency'], vals['seconds']) < 0 or vals['served'] > vals['gap']:
                problems.append({'line': line, 'check': 'service_or_resource_bounds'})
            if vals['gap'] and not close(vals['satisfaction'], vals['served']/vals['gap']):
                problems.append({'line': line, 'check': 'service_ratio'})
            if row['valid'].lower() != 'true':
                problems.append({'line': line, 'check': 'upstream_valid_is_not_true'})
            groups[(row['panel'], row['arm'])].append(vals)
        except (ValueError, KeyError, TypeError) as exc:
            problems.append({'line': line, 'check': 'invalid_row', 'detail': str(exc)})
    return problems, {'groups': [{'panel': k[0], 'arm': k[1], 'n': len(v),
                                 'mean_J': statistics.mean(r['J'] for r in v),
                                 'max_seconds': max(r['seconds'] for r in v)} for k, v in sorted(groups.items())],
                      'local_component': 'may be negative: incremental local impact, not gross cost',
                      'physical_revalidation': 'NOT_CHECKED; original valid field only'}


def paired_checks(rows):
    problems, groups, seen = [], defaultdict(list), set()
    for line, row in enumerate(rows, 2):
        try:
            value = number(row['delta_net_CNY'])
            key = tuple(row[k] for k in ('run_id', 'baseline_run_id', 'window'))
            if key in seen:
                problems.append({'line': line, 'check': 'duplicate_pair'})
            seen.add(key)
            if not close(value/10000, number(row['delta_net_wanyuan'])):
                problems.append({'line': line, 'check': 'currency_unit_conversion'})
            groups[(row['window'], row['baseline'])].append(value)
        except (ValueError, KeyError, TypeError) as exc:
            problems.append({'line': line, 'check': 'invalid_row', 'detail': str(exc)})
    return problems, {'groups': [{'window': k[0], 'baseline': k[1], 'n': len(v),
                                 'positive': sum(x > 0 for x in v), 'negative': sum(x < 0 for x in v),
                                 'mean_delta_CNY': statistics.mean(v), 'min_delta_CNY': min(v), 'max_delta_CNY': max(v)}
                                for k, v in sorted(groups.items())],
                      'boundary': 'No pooled percentage, independence claim or significance test.'}


def audit(project_root, bindings):
    results = []
    functions = {'daily': daily_checks, 'trips': lambda rows: trip_checks(rows, bindings['vehicle']['kg'], bindings['vehicle']['m3']),
                 'forecast': forecast_checks, 'emergency': emergency_checks, 'paired': paired_checks}
    for key, spec in bindings['datasets'].items():
        path = Path(project_root) / spec['path']
        item = {'dataset': key, 'path': spec['path'], 'declared_scope': spec['scope']}
        if not path.is_file():
            item.update(status='NOT_CHECKED', reason='File missing')
        else:
            try:
                digest = sha256(path)
                with path.open(encoding='utf-8-sig', newline='') as f:
                    rows = list(csv.DictReader(f))
                if not rows:
                    raise ValueError('empty dataset')
                issues, metrics = functions[key](rows)
                item.update(status='FAIL' if issues else 'PASS', rows=len(rows), sha256=digest,
                            binding_hash_matches=digest == spec.get('sha256'),
                            issue_count=len(issues), issues=issues[:30], metrics=metrics)
            except (ValueError, KeyError, TypeError, OSError, csv.Error) as exc:
                item.update(status='FAIL', reason=str(exc))
        results.append(item)
    return {'schema_version': 1, 'generated_at': datetime.now(timezone.utc).isoformat(),
            'mode': 'offline_result_audit', 'production_state_mutated': False,
            'checks': results, 'limitations': ['No solver was rerun.', 'No physical layout certificate was reconstructed.',
            'Declared data scopes need rechecking when binding_hash_matches is false.',
            'Accounting consistency is not causal evidence or production certification.']}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project-root', required=True, type=Path)
    p.add_argument('--bindings', required=True, type=Path, help='Explicit local dataset binding; no private default data')
    p.add_argument('--out', required=True, type=Path)
    a = p.parse_args()
    bindings = json.loads(a.bindings.read_text(encoding='utf-8-sig'))
    result = audit(a.project_root, bindings)
    a.out.mkdir(parents=True, exist_ok=False)
    (a.out/'audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    lines = ['# 日日顺现有结果复核', '', '类型：离线审查；未修改原数据，未重新求解。', '',
             '| 数据 | 来源口径 | 行数 | 结果 |', '|---|---|---:|---|']
    for r in result['checks']:
        lines.append(f"| {r['dataset']} | {r['declared_scope']} | {r.get('rows','—')} | {r['status']} |")
    for r in result['checks']:
        lines += ['', '## '+r['dataset'], '', '```json', json.dumps(r, ensure_ascii=False, indent=2), '```']
    lines += ['', '## 限制', '', *['- '+s for s in result['limitations']]]
    (a.out/'audit.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({'report': str(a.out/'audit.json'), 'checks': [{k:r.get(k) for k in ('dataset','status','rows','issue_count')} for r in result['checks']]}, ensure_ascii=False))
    return 1 if any(r['status'] == 'FAIL' for r in result['checks']) else 0


if __name__ == '__main__':
    raise SystemExit(main())
