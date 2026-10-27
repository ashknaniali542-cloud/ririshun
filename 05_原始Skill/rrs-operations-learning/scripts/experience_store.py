"""Evidence-bound experience validation and retrieval; never executes stored text."""
import argparse
import copy
import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path

SCOPES = {'enterprise_records', 'enterprise_execution', 'enterprise_calibrated_scenarios', 'research_simulation', 'synthetic_development'}
MODULES = {'routine', 'forecast', 'emergency', 'packing'}


def read_json(path):
    def invalid(value):
        raise ValueError('Non-finite JSON value: '+value)
    return json.loads(Path(path).read_text(encoding='utf-8-sig'), parse_constant=invalid)


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def content_hash(entry):
    payload = {k:v for k,v in entry.items() if k not in ('status', 'validation', 'available_at')}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def timestamp(value):
    d = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if d.tzinfo is None:
        raise ValueError('Timezone required')
    return d


def resolve(base, value):
    path = Path(value)
    return path if path.is_absolute() else Path(base)/path


def ensure(condition, message):
    if not condition:
        raise ValueError(message)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def evidence_check(reference, base):
    ensure(isinstance(reference, dict), 'Invalid evidence reference')
    ensure(nonempty(reference.get('path')), 'Missing evidence path')
    digest = reference.get('sha256', '')
    ensure(isinstance(digest, str) and re.fullmatch('[0-9a-f]{64}', digest), 'Invalid evidence hash')
    path = resolve(base, reference['path'])
    ensure(path.is_file(), 'Missing evidence: '+reference['path'])
    ensure(file_hash(path) == digest, 'Evidence changed: '+reference['path'])
    return path


def validate_report(entry, report):
    ensure(report.get('schema_version') == 1, 'Invalid validation schema')
    ensure(report.get('entry_id') == entry['id'] and report.get('kind') == entry['kind'], 'Validation entry/kind mismatch')
    ensure(report.get('entry_content_sha256') == content_hash(entry), 'Experience content changed after validation')
    ensure(report.get('result') == 'pass' and nonempty(report.get('reviewer')), 'Missing successful review')
    timestamp(report['validated_at'])
    ensure(report.get('source_scope') == entry['source_scope'], 'Validation source scope mismatch')
    ensure(report.get('target_scopes') == entry['target_scopes'], 'Validation target scopes mismatch')
    ensure(report.get('applicability') == entry['applicability'], 'Validation configuration mismatch')
    ensure(report.get('evidence_sha256') == sorted(x['sha256'] for x in entry['evidence']), 'Validation evidence mismatch')
    checks = report.get('checks')
    ensure(isinstance(checks, list) and checks, 'No validation checks')
    ensure(all(isinstance(c,dict) and c.get('passed') is True and nonempty(c.get('name')) and nonempty(c.get('detail')) for c in checks), 'Failed/incomplete validation checks')
    if entry['kind'] == 'procedure':
        ensure(report.get('method') in ('source_and_test', 'deterministic_audit'), 'Invalid procedure validation method')
    else:
        ensure(report.get('method') == 'heldout_replay', 'Policy requires held-out replay')
        ensure(report.get('split') in ('heldout', 'future_window'), 'Policy requires independent validation window')
        ensure(report.get('causal_cutoff_passed') is True and report.get('constraint_checks_passed') is True, 'Policy causal/constraint checks missing')
        ensure(all(nonempty(report.get(k)) for k in ('baseline_run_id', 'candidate_run_id', 'comparison_scope')), 'Policy matched baseline missing')
        ensure(report['baseline_run_id'] != report['candidate_run_id'], 'Candidate equals baseline')
        metric = report.get('metric', {})
        ensure(nonempty(metric.get('name')) and nonempty(metric.get('unit')), 'Policy metric missing')
        b, c = metric.get('baseline'), metric.get('candidate')
        ensure(type(b) in (int,float) and type(c) in (int,float) and math.isfinite(b) and math.isfinite(c), 'Policy metric non-finite')
        ensure(metric.get('direction') in ('higher','lower'), 'Metric direction missing')
        ensure(c > b if metric['direction'] == 'higher' else c < b, 'No improvement under stated metric')
        ensure(report.get('acceptance_passed') is True, 'Policy acceptance not passed')


def check_entry(entry, base, require_validated=False):
    errors = []
    try:
        ensure(isinstance(entry, dict), 'Entry must be an object')
        ensure(entry.get('schema_version') == 1, 'Invalid entry schema')
        ensure(isinstance(entry.get('id'),str) and re.fullmatch('[a-z0-9][a-z0-9-]{0,63}', entry['id']), 'Invalid id')
        ensure(isinstance(entry.get('version'),str) and re.fullmatch(r'\d+\.\d+\.\d+', entry['version']), 'Invalid version')
        ensure(nonempty(entry.get('title')), 'Title missing')
        ensure(entry.get('module') in MODULES, 'Unknown module')
        ensure(entry.get('kind') in ('procedure', 'policy_hypothesis'), 'Unknown kind')
        ensure(entry.get('status') in ('draft', 'validated', 'rejected', 'deprecated'), 'Unknown status')
        if require_validated:
            ensure(entry['status'] == 'validated', 'Not a validated experience')
        ensure(entry.get('source_scope') in SCOPES, 'Unknown source scope')
        targets = entry.get('target_scopes')
        ensure(isinstance(targets,list) and targets and all(x in SCOPES for x in targets), 'Invalid target scopes')
        ensure(set(targets) == {entry['source_scope']}, 'Cross-source transfer requires separate evidence and a separately validated entry')
        available = timestamp(entry['available_at'])
        ensure(isinstance(entry.get('applicability'),dict) and entry['applicability'], 'Applicability missing')
        ensure(all(nonempty(k) and type(v) in (str,int,float,bool) and (type(v) is not float or math.isfinite(v)) for k,v in entry['applicability'].items()), 'Invalid applicability values')
        triggers = entry.get('triggers')
        ensure(isinstance(triggers,list) and triggers, 'Triggers missing')
        for trigger in triggers:
            ensure(isinstance(trigger,dict) and nonempty(trigger.get('field')) and trigger.get('op') in ('eq','gt','gte','lt','lte','in') and 'value' in trigger, 'Invalid trigger')
            value = trigger['value']
            if trigger['op'] == 'in':
                ensure(isinstance(value,list) and value and all(type(v) in (str,int,float,bool) for v in value), 'Invalid membership trigger')
            elif trigger['op'] != 'eq':
                ensure(type(value) in (int,float) and math.isfinite(value), 'Invalid numeric trigger')
            else:
                ensure(type(value) in (str,int,float,bool), 'Invalid equality trigger')
        ensure(isinstance(entry.get('evidence'),list) and entry['evidence'], 'Evidence missing')
        for reference in entry['evidence']:
            evidence_check(reference, base)
            ensure(nonempty(reference.get('detail')), 'Evidence explanation missing')
        for field in ('steps','constraints'):
            ensure(isinstance(entry.get(field),list) and entry[field] and all(nonempty(v) for v in entry[field]), field+' missing')
        ensure(isinstance(entry.get('not_applicable'),list) and all(nonempty(v) for v in entry['not_applicable']), 'not_applicable must be a list')
        if entry['status'] == 'validated':
            report_path = evidence_check(entry.get('validation'), base)
            report = read_json(report_path)
            validate_report(entry, report)
            ensure(available >= timestamp(report['validated_at']), 'Knowledge availability predates validation')
    except (ValueError, KeyError, TypeError, OSError, AttributeError) as exc:
        errors.append(str(exc))
    return errors


def promote(entry, validation_path, base):
    ensure(entry.get('status') == 'draft', 'Only draft entries can be promoted; create a new version for revisions')
    errors = check_entry(entry, base)
    ensure(not errors, '; '.join(errors))
    report = read_json(validation_path)
    validate_report(entry, report)
    promoted = copy.deepcopy(entry)
    promoted['status'] = 'validated'
    promoted['available_at'] = max(timestamp(entry['available_at']), timestamp(report['validated_at'])).isoformat()
    path = Path(validation_path).resolve()
    try:
        relative = str(path.relative_to(Path(base).resolve())).replace('\\', '/')
    except ValueError:
        relative = str(path)
    promoted['validation'] = {'path': relative, 'sha256': file_hash(path)}
    ensure(not check_entry(promoted,base,True), 'Promotion self-check failed')
    return promoted


def trigger_matches(trigger, context):
    key, op, ref = trigger['field'], trigger['op'], trigger['value']
    if key not in context:
        return False
    value = context[key]
    if op == 'eq':
        return type(value) is type(ref) and value == ref
    if op == 'in':
        return any(type(value) is type(x) and value == x for x in ref)
    if type(value) not in (int,float) or type(ref) not in (int,float) or not math.isfinite(value):
        return False
    return {'gt':lambda:value>ref, 'gte':lambda:value>=ref, 'lt':lambda:value<ref, 'lte':lambda:value<=ref}[op]()


def retrieve(store, context):
    cutoff = timestamp(context['knowledge_cutoff'])
    ensure(context.get('module') in MODULES and context.get('source_scope') in SCOPES, 'Context module/scope required')
    matches, excluded = [], []
    for path in sorted(Path(store).rglob('*.json')):
        if any(x in ('evidence', 'validation', 'contexts') for x in path.relative_to(store).parts):
            continue
        label = path.relative_to(store).as_posix()
        try:
            entry = read_json(path)
            reasons = check_entry(entry, store, True)
            if not reasons:
                if entry['module'] != context['module']:
                    reasons.append('module mismatch')
                if context['source_scope'] not in entry['target_scopes']:
                    reasons.append('source scope mismatch')
                if timestamp(entry['available_at']) > cutoff:
                    reasons.append('experience not available at decision cutoff')
                if any(k not in context or type(context[k]) is not type(v) or context[k] != v for k,v in entry['applicability'].items()):
                    reasons.append('configuration mismatch or missing field')
                if not all(trigger_matches(t,context) for t in entry['triggers']):
                    reasons.append('trigger conditions unmet')
            if reasons:
                excluded.append({'path':label, 'reasons':reasons})
                continue
            text = entry['title']+' '+' '.join(entry['steps'])
            tokens = re.findall(r'[A-Za-z0-9_]+|[\u4e00-\u9fff]{1,2}', context.get('query','').lower())
            score = sum(t in text.lower() for t in set(tokens))
            matches.append({'id':entry['id'], 'version':entry['version'], 'title':entry['title'], 'score':score,
                            'path':label, 'steps':entry['steps'], 'constraints':entry['constraints'],
                            'not_applicable':entry['not_applicable'], 'evidence':entry['evidence']})
        except (ValueError, KeyError, TypeError, OSError) as exc:
            excluded.append({'path':label, 'reasons':['invalid JSON/entry: '+str(exc)]})
    newest = {}
    for hit in matches:
        prior = newest.get(hit['id'])
        version = lambda x:tuple(map(int,x['version'].split('.')))
        if prior is None or version(hit) > version(prior):
            if prior:
                excluded.append({'path':prior['path'], 'reasons':['superseded matching version']})
            newest[hit['id']] = hit
        else:
            excluded.append({'path':hit['path'], 'reasons':['superseded matching version']})
    return {'schema_version':1, 'retrieval_method':'explicit_conditions_then_lexical_ranking', 'executable':False,
            'matches':sorted(newest.values(),key=lambda x:(-x['score'],x['id'])), 'excluded':excluded}


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x',encoding='utf-8') as f:
        f.write(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command',required=True)
    for command in ('check','promote','digest'):
        p = sub.add_parser(command)
        p.add_argument('--entry',required=True,type=Path)
        if command != 'digest':
            p.add_argument('--base',required=True,type=Path)
        if command == 'promote':
            p.add_argument('--validation',required=True,type=Path)
            p.add_argument('--out',required=True,type=Path)
    p = sub.add_parser('retrieve')
    p.add_argument('--store',required=True,type=Path)
    p.add_argument('--context',required=True,type=Path)
    p.add_argument('--out',type=Path)
    a = parser.parse_args()
    try:
        if a.command == 'check':
            errors = check_entry(read_json(a.entry),a.base)
            result = {'valid':not errors, 'errors':errors}
        elif a.command == 'digest':
            result = {'entry_content_sha256':content_hash(read_json(a.entry))}
        elif a.command == 'promote':
            result = promote(read_json(a.entry),a.validation,a.base)
            write_new(a.out,result)
        else:
            ensure(a.store.is_dir(), 'Experience store does not exist')
            result = retrieve(a.store,read_json(a.context))
            if a.out:
                write_new(a.out,result)
        print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
        return int(a.command == 'check' and bool(result['errors']))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(json.dumps({'error':str(exc)},ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
