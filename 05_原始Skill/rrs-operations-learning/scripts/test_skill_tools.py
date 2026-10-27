"""Behavioral tests: evidence, temporal isolation and RRS numerical invariants."""
import json
import os
import uuid
import tempfile
import shutil
import unittest
from pathlib import Path
import experience_store as s
from rrs_audit import daily_checks, trip_checks, forecast_checks, emergency_checks


class ExperienceTests(unittest.TestCase):
    def setUp(self):
        base=Path(os.environ.get('RRS_TEST_DIR',str(Path(tempfile.gettempdir())/'rrs-method-tests'))).resolve()
        self.root=base/uuid.uuid4().hex
        self.root.mkdir(parents=True)
        def cleanup():
            target=self.root.resolve()
            if target == base or not target.is_relative_to(base):
                raise RuntimeError('Refusing cleanup outside test directory')
            shutil.rmtree(target)
        self.addCleanup(cleanup)
        (self.root/'evidence').mkdir(); (self.root/'validation').mkdir()
        f=self.root/'evidence/source.txt'; f.write_text('observed evidence')
        self.e=dict(schema_version=1,id='routine-check',version='1.0.0',title='库存复盘',module='routine',kind='procedure',status='draft',source_scope='research_simulation',target_scopes=['research_simulation'],available_at='2026-10-27T10:00:00+08:00',applicability={'inventory_rule':'E_N_v1'},triggers=[{'field':'task','op':'eq','value':'review'}],evidence=[{'path':'evidence/source.txt','sha256':s.file_hash(f),'detail':'fixture'}],steps=['核对库存'],constraints=['不使用未来数据'],not_applicable=[],validation=None)
        self.v=dict(schema_version=1,entry_id=self.e['id'],kind='procedure',entry_content_sha256=s.content_hash(self.e),result='pass',reviewer='fixture',validated_at='2026-10-27T11:00:00+08:00',source_scope='research_simulation',target_scopes=['research_simulation'],applicability=self.e['applicability'],evidence_sha256=[self.e['evidence'][0]['sha256']],checks=[{'name':'fixture','passed':True,'detail':'deterministic fixture'}],method='deterministic_audit')
        self.c=dict(module='routine',source_scope='research_simulation',knowledge_cutoff='2026-10-28T00:00:00+08:00',inventory_rule='E_N_v1',task='review',query='库存')
    def promote(self):
        p=self.root/'validation/report.json'; p.write_text(json.dumps(self.v))
        return s.promote(self.e,p,self.root)
    def save(self,e):
        (self.root/'entry.json').write_text(json.dumps(e))
    def test_validated_retrieved(self):
        self.save(self.promote()); r=s.retrieve(self.root,self.c)
        self.assertEqual(len(r['matches']),1); self.assertFalse(r['executable'])
    def test_retrieval_paths_relative(self):
        self.save(self.promote()); r=s.retrieve(self.root,self.c)
        self.assertEqual(r['matches'][0]['path'],'entry.json')
        self.assertFalse(Path(r['matches'][0]['path']).is_absolute())
    def test_draft_excluded(self):
        self.save(self.e); self.assertFalse(s.retrieve(self.root,self.c)['matches'])
    def test_changed_evidence(self):
        e=self.promote(); (self.root/'evidence/source.txt').write_text('changed')
        self.assertIn('Evidence changed',s.check_entry(e,self.root)[0])
    def test_changed_steps(self):
        e=self.promote(); e['steps']=['different']; self.assertIn('content changed',s.check_entry(e,self.root)[0])
    def test_temporal_leakage(self):
        self.save(self.promote()); self.c['knowledge_cutoff']='2026-10-27T10:30:00+08:00'
        self.assertFalse(s.retrieve(self.root,self.c)['matches'])
    def test_simulation_not_production(self):
        self.save(self.promote()); self.c['source_scope']='enterprise_execution'
        self.assertFalse(s.retrieve(self.root,self.c)['matches'])
    def test_changed_configuration(self):
        self.save(self.promote()); self.c['inventory_rule']='different'
        self.assertFalse(s.retrieve(self.root,self.c)['matches'])
    def test_missing_configuration(self):
        self.save(self.promote()); del self.c['inventory_rule']
        self.assertFalse(s.retrieve(self.root,self.c)['matches'])
    def test_deprecated_excluded(self):
        e=self.promote(); e['status']='deprecated'; self.save(e)
        self.assertFalse(s.retrieve(self.root,self.c)['matches'])
    def test_boolean_not_numeric(self):
        self.assertFalse(s.trigger_matches({'field':'gap','op':'gt','value':0},{'gap':True}))
    def test_policy_needs_heldout(self):
        self.e['kind']='policy_hypothesis'; self.v['kind']='policy_hypothesis'; self.v['entry_content_sha256']=s.content_hash(self.e)
        with self.assertRaisesRegex(ValueError,'held-out'): self.promote()
    def test_failed_check_rejected(self):
        self.v['checks'][0]['passed']=False
        with self.assertRaisesRegex(ValueError,'Failed'): self.promote()
    def test_mismatched_report(self):
        self.v['entry_id']='other'
        with self.assertRaisesRegex(ValueError,'mismatch'): self.promote()
    def test_timezone_required(self):
        self.e['available_at']='2026-10-27T10:00:00'
        self.assertIn('Timezone',s.check_entry(self.e,self.root)[0])
    def test_no_overwrite(self):
        p=self.root/'keep.json'; s.write_new(p,{'original':1})
        with self.assertRaises(FileExistsError): s.write_new(p,{'original':2})
        self.assertEqual(s.read_json(p),{'original':1})
    def test_nan_json_rejected(self):
        p=self.root/'bad.json'; p.write_text('{"value":NaN}')
        with self.assertRaises(ValueError): s.read_json(p)


class AuditTests(unittest.TestCase):
    def day(self,d='2025-10-01'):
        return dict(run_id='r',date=d,request='10',sales='8',lost='2',closing_E='10',closing_N='0',factory_receipt='0',warehouse_receipt='0',warehouse_out='0',sales_contribution='80',warehouse_transport_cost='10',net_contribution='70')
    def test_inventory_balance(self):
        a=self.day(); b=self.day('2025-10-02'); b['closing_E']='2'
        self.assertFalse(daily_checks([a,b])[0]); b['closing_E']='3'
        self.assertIn('network_inventory_balance',[x['check'] for x in daily_checks([a,b])[0]])
    def test_accounting_errors(self):
        a=self.day(); a['lost']='3'; a['net_contribution']='80'; names=[x['check'] for x in daily_checks([a])[0]]
        self.assertIn('request_sales_lost',names); self.assertIn('net_contribution_balance',names)
    def test_duplicate_day(self):
        self.assertIn('duplicate_run_date',[x['check'] for x in daily_checks([self.day(),self.day()])[0]])
    def trip(self):
        return dict(run_id='r',date='2025-10-01',trip_id='t',source='a',destination='b',available='2025-10-02',quantity='1',quantity_vector='[1,0]',SKU_count='1',weight_kg='5000',volume_m3='30',cost_CNY='300')
    def test_resource_not_geometry(self):
        r=self.trip(); errors,m=trip_checks([r],5000,30)
        self.assertFalse(errors); self.assertEqual(m['geometry_status'],'NOT_CHECKED')
        r['weight_kg']='5001'; self.assertIn('vehicle_capacity',[x['check'] for x in trip_checks([r],5000,30)[0]])
    def test_quantity_vector(self):
        r=self.trip(); r['quantity_vector']='[0,0]'
        self.assertIn('quantity_vector_balance',[x['check'] for x in trip_checks([r],5000,30)[0]])
    def test_nonfinite_forecast(self):
        r=dict(node='n',date='2025-10-01',actual='1',selected='NaN',lower='0',upper='2')
        self.assertTrue(forecast_checks([r])[0])
    def test_negative_local_is_allowed(self):
        r=dict(J='10',emergency='0',local='-10',transport='20',gap='5',served='5',satisfaction='1',seconds='1',valid='True',panel='DEV',arm='a')
        self.assertFalse(emergency_checks([r])[0])


if __name__=='__main__': unittest.main(verbosity=2)
