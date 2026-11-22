#!/usr/bin/env python3
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from worker_profile import ASSETS, ProfileError, load_json, validate_profile_document
from worker_route import prepare, validate_table

class RouterTests(unittest.TestCase):
    def setUp(self):
        self.doc = load_json(ASSETS / 'worker-profile-example.json')
        self.table = load_json(ASSETS / 'worker-routing-table.json')
        # Isolate legacy synthetic fixtures from the now usable packaged policy.
        self.table['entries'] = [r for r in self.table['entries'] if r['family'] == 'general']
        for row in self.table['entries']:
            row['candidates'] = row['candidates'][:1]
            c = row['candidates'][0]
            c.update(input_modalities=['text'], output_modalities=['text'], capabilities=['general.execute'], evidence=['synthetic test assertion'])
    def test_difficulties_and_hashes(self):
        results=[]
        for d in ('easy','medium','hard'):
            self.doc['units'][0]['profile']['difficulty']=d
            result=prepare(self.doc,self.table); self.assertEqual(result,prepare(self.doc,self.table)); results.append(result['results'][0]['selected'])
            self.assertEqual(len(result['profile_sha256']),64)
        self.assertEqual([(r['model'],r['effort']) for r in results],[('gpt-6.1-terra','low'),('gpt-6.1-terra','medium'),('gpt-6.2-sol','high')])
        print('synthetic general difficulty identities:',results)
    def test_multimodal_and_filtering(self):
        p=self.doc['units'][0]['profile']; p.update(family='code',input_modalities=['image','text'],output_modalities=['code'],required_capabilities=['vision.read','frontend.code','screenshot_to_code','framework.react'],required_tools=['repo'],context_requirement=20,hard_constraints=['sandbox'])
        base=self.table['entries'][0]['candidates'][0]
        allc=copy.deepcopy(base); allc.update(input_modalities=['image','text'],output_modalities=['code'],capabilities=p['required_capabilities'],tools=['repo'],context_limit=20,constraints=['sandbox'])
        incomplete=copy.deepcopy(allc); incomplete['identity']={'route':'codex','model':'gpt-6.1-sol','effort':'high'}; incomplete['capabilities']=['vision.read']
        row={'family':'code','difficulty':'easy','candidates':[incomplete]}; self.table['entries'].append(row)
        self.assertEqual(prepare(self.doc,self.table)['results'][0]['status'],'NO_MATCH')
        row['candidates'].append(allc)
        result=prepare(self.doc,self.table)['results'][0]; self.assertEqual(result['status'],'MATCH'); self.assertEqual(len(result['rejected']),1)
        allc['input_modalities']=['text']; allc['output_modalities']=['code','image']; self.assertEqual(prepare(self.doc,self.table)['results'][0]['status'],'NO_MATCH')
        print('synthetic multimodal negative/positive: NO_MATCH/MATCH; reversed direction NO_MATCH')
    def test_invalid_profile(self):
        for key,val,code in [('difficulty','unknown','PROFILE_INCOMPLETE'),('family','unknown','UNSUPPORTED_PROFILE'),('required_capabilities',['bogus'],'UNSUPPORTED_PROFILE'),('uncertainties',['unknown permission'],'PROFILE_INCOMPLETE')]:
            d=copy.deepcopy(self.doc); d['units'][0]['profile'][key]=val
            with self.subTest(key=key), self.assertRaises(ProfileError) as e: validate_profile_document(d)
            self.assertEqual(e.exception.code,code)
        for key in ('done_when','inputs','deliverables'):
            d=copy.deepcopy(self.doc); d['units'][0][key]=[]
            with self.subTest(key=key), self.assertRaises(ProfileError): validate_profile_document(d)
    def test_dag(self):
        d=copy.deepcopy(self.doc); d['units'][0]['depends_on']=['missing']
        with self.assertRaises(ProfileError): validate_profile_document(d)
        d=copy.deepcopy(self.doc); d['units'].append(copy.deepcopy(d['units'][0]))
        with self.assertRaises(ProfileError): validate_profile_document(d)
        d['units'][1]['id']='two'; d['units'][0]['depends_on']=['two']; d['units'][1]['depends_on']=['one']
        with self.assertRaises(ProfileError): validate_profile_document(d)
    def test_table_errors_and_no_match(self):
        t=copy.deepcopy(self.table); t['version']=1
        with self.assertRaises(ProfileError): validate_table(t)
        t=copy.deepcopy(self.table); t['entries'].append(copy.deepcopy(t['entries'][0]))
        with self.assertRaises(ProfileError): validate_table(t)
        t=copy.deepcopy(self.table); t['entries'][0]['candidates'].append(copy.deepcopy(t['entries'][0]['candidates'][0]))
        with self.assertRaises(ProfileError): validate_table(t)
        t=copy.deepcopy(self.table); t['entries'][0]['candidates'][0]['enabled']=False
        self.assertEqual(prepare(self.doc,t)['results'][0]['status'],'NO_MATCH')
        self.doc['units'][0]['profile']['family']='language'; self.assertEqual(prepare(self.doc,t)['results'][0]['status'],'NO_MATCH')
    def test_ties_pins_and_resources(self):
        row=self.table['entries'][0]; c=copy.deepcopy(row['candidates'][0]); c['identity']['model']='gpt-6.1-sol'; row['candidates'].insert(0,c)
        result=prepare(self.doc,self.table); self.assertEqual(result['results'][0]['selected']['model'],'gpt-6.1-sol')
        pin=row['candidates'][1]['identity']; self.assertEqual(prepare(self.doc,self.table,{'one':pin})['results'][0]['selected'],pin)
        row['candidates'][1]['enabled']=False; self.assertEqual(prepare(self.doc,self.table,{'one':pin})['results'][0]['status'],'NO_MATCH')
        with self.assertRaises(ProfileError): prepare(self.doc,self.table,{'missing':pin})
        self.doc['units'][0]['profile']['required_tools']=['not-provided']; self.assertEqual(prepare(self.doc,self.table)['results'][0]['status'],'NO_MATCH')
    def test_families_and_unknown_context(self):
        for family, capability in [('language','text.translate'),('structured_data','data.transform'),('code','repository.edit'),('general','general.execute')]:
            d=copy.deepcopy(self.doc); p=d['units'][0]['profile']; p['family']=family; p['required_capabilities']=[capability]
            validate_profile_document(d)
        self.doc['units'][0]['profile']['context_requirement']='unknown'
        with self.assertRaises(ProfileError) as e: validate_profile_document(self.doc)
        self.assertEqual(e.exception.code,'PROFILE_INCOMPLETE')
    def test_default_matches_but_is_not_capability_certification(self):
        result = prepare(self.doc, load_json(ASSETS/'worker-routing-table.json'))
        self.assertEqual(result['results'][0]['status'], 'MATCH')
        self.assertIn('proposal only', result['authority'])
        self.assertTrue(any('editorial_prior' in e for e in result['results'][0]['evidence']))
    def test_explicit_codex_availability_preserves_ranking_pins_and_unknown_routes(self):
        table = load_json(ASSETS/'worker-routing-table.json')
        available = {'gpt-6.1-terra': ['medium'], 'gpt-6.2-sol': ['low']}
        result = prepare(self.doc, table, codex_availability=available)['results'][0]
        self.assertEqual(result['selected'], {'route': 'codex', 'model': 'gpt-6.2-sol', 'effort': 'low'})
        self.assertIn('not listed in Codex availability', result['rejected'][0]['reasons'])
        pin = {'one': result['selected']}
        self.assertEqual(prepare(self.doc, table, pin, codex_availability=available)['results'][0]['selected'],
                         pin['one'])
        self.assertEqual(prepare(self.doc, table, pin, codex_availability={})['results'][0]['status'], 'NO_MATCH')
        self.assertEqual(prepare(self.doc, table, codex_availability={})['results'][0]['selected']['route'], 'agy')
        for malformed in ([], {'terra': []}, {'terra': ['low', 'low']}, {'terra': ['low', False]}):
            with self.subTest(malformed=malformed), self.assertRaises(ProfileError):
                prepare(self.doc, table, codex_availability=malformed)

    def test_availability_cli_proposal_and_profile_binding_compatibility(self):
        with tempfile.TemporaryDirectory() as folder:
            availability = Path(folder) / 'availability.json'
            availability.write_text('{"gpt-6.2-sol":["low"]}')
            pin = Path(folder) / 'pins.json'
            pin.write_text('{"one":{"route":"codex","model":"gpt-6.1-terra","effort":"low"}}')
            source = ASSETS/'worker-profile-example.json'
            def command(script, action, *extra):
                tool = Path(__file__).with_name(script)
                return subprocess.run([sys.executable, '-B', str(tool), action, str(source), *extra],
                                      capture_output=True, text=True)
            selected = command('worker_route.py', 'prepare', '--codex-availability', str(availability))
            self.assertEqual(selected.returncode, 0, selected.stderr + selected.stdout)
            proposal = json.loads(selected.stdout)['results'][0]['selected']
            legacy = command('record_check.py', 'profile-prepare', '--unit', 'one')
            new = command('record_check.py', 'profile-prepare', '--unit', 'one', '--codex-availability', str(availability))
            for proc in (legacy, new):
                self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            old, bound = (json.loads(proc.stdout)['profile_binding'] for proc in (legacy, new))
            self.assertEqual(old['version'], 3)
            self.assertNotIn('codex_availability', old)
            self.assertEqual(bound['version'], 4)
            self.assertEqual(bound['selected'], proposal)
            self.assertEqual(bound['codex_availability'], {'gpt-6.2-sol': ['low']})
            mismatch = command('record_check.py', 'profile-prepare', '--unit', 'one', '--pins', str(pin),
                               '--codex-availability', str(availability))
            self.assertEqual(mismatch.returncode, 1, mismatch.stdout + mismatch.stderr)
            self.assertEqual(json.loads(mismatch.stdout)['errors'][0]['code'], 'NO_MATCH')
            availability.write_text('{"gpt-6.2-sol":["low"],"gpt-6.2-sol":["low"]}')
            duplicate = command('worker_route.py', 'prepare', '--codex-availability', str(availability))
            self.assertEqual(duplicate.returncode, 1, duplicate.stdout + duplicate.stderr)
            self.assertIn('duplicate JSON key', duplicate.stdout)

    def test_cli(self):
        path=Path(__file__).with_name('worker_profile.py')
        r=subprocess.run([sys.executable,str(path),'validate',str(ASSETS/'worker-profile-example.json')],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        path=path.with_name('worker_route.py'); r=subprocess.run([sys.executable,str(path),'prepare',str(ASSETS/'worker-profile-example.json')],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr); self.assertEqual(json.loads(r.stdout)['results'][0]['status'],'MATCH')

if __name__=='__main__': unittest.main()
