"""Lifecycle fixtures only; actor/approval strings are NOT real consent."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import stat
import unittest
from unittest.mock import patch

from test_native_operations import NativeCase, PACKAGE, digest, pin, save, tree
import run_completion as rc
import native_storage as storage
import completion_hook as hook


class StorageLifecycleTests(NativeCase):
    def setUp(self):
        super().setUp()
        self.home = self.root / 'sejong'
        self.run_root = self.home / 'runs/fixture'
        self.run_root.mkdir(parents=True)
        self.cwd = self.root / 'workspace'; self.cwd.mkdir()
        self.identity = save(self.root / 'identity.json', dict(host='explicit_lead', session_id='fixture-session', cwd=str(self.cwd)))
        self.enrollment = dict(schema='company-native-storage-enrollment/v1', sejong_home=str(self.home), run=str(self.run_root), run_id='goal-1', owner='B', record='record.json', host='explicit_lead', session_id='fixture-session', cwd=str(self.cwd), consumers=[], expect_session_binding_sha256=None, identity_evidence=pin(self.identity))
        self.enroll_path = save(self.root / 'enroll.json', self.enrollment)
        self.config = self.root / 'user.md'; self.config.write_text('---\nschema_version: 1\npreset: single\nservices: ["antigravity"]\n---\n')
        self.env['AGENT_COMPANY_CONFIG'] = str(self.config)
        self.enterContext(patch.dict(os.environ, {'AGENT_COMPANY_CONFIG':str(self.config)}))

    def enroll(self, expected=0):
        save(self.enroll_path, self.enrollment)
        return self.cli('storage', 'enroll', '--request', self.enroll_path, expected=expected)

    def artifact(self, path, kind='preserve', consumers=None):
        return dict(path=path, **{'class':kind}, owner='B', consumers=consumers or [], reason='fixture exact declared role', origin='fixture producer', regeneration=pin(self.identity) if kind=='recreatable' else None, next_use_or_recheck='at acceptance')

    def classify(self, artifacts, phase='reserve', expected=0):
        request = dict(schema='company-native-storage-classification/v1', enrollment=pin(self.enroll_path), expect_manifest_sha256=digest(self.run_root / rc.MANIFEST), phase=phase, artifacts=artifacts)
        path = save(self.root / 'classify.json', request)
        return self.cli('storage','classify','--request',path,expected=expected)

    def close(self, enrollment=True, trigger=None, expected=0):
        request = dict(schema='company-native-storage-closeout-request/v1', enrollment=pin(self.enroll_path) if enrollment else None, sejong_home=str(self.home), session_id=self.enrollment['session_id'], cwd=str(self.cwd), run=str(self.run_root), run_id='goal-1', owner='B', record='record.json', trigger=trigger)
        return self.cli('storage','closeout','--request',save(self.root/'closeout.json',request),expected=expected)

    def accepted(self, disposable=True):
        self.enroll()
        artifacts=[self.artifact('report.md'),self.artifact('acceptance.json')]
        if disposable: artifacts.append(self.artifact('scratch/raw','recreatable'))
        self.classify(artifacts)
        (self.run_root/'scratch').mkdir()
        (self.run_root/'report.md').write_bytes(b'retained evidence')
        (self.run_root/'acceptance.json').write_bytes(b'{"accepted":true}')
        if disposable: (self.run_root/'scratch/raw').write_bytes(b'disposable only')
        self.classify(artifacts,'freeze')
        from test_run_completion import ordinary_routing
        cases=json.loads((PACKAGE/'assets/record-cases.json').read_bytes())['cases']
        record=copy.deepcopy(next((x['record'] for x in cases if x['name']=='required-resource-record-valid'), cases[0]['record']))
        record.update(label='real',resource_accounting='required',routing_accounting='required')
        record['goal'].update(status='succeeded',known_failure=False); record['goal']['assessment'].update(verdict='succeeded')
        for row in record['evidence'].values(): row['kind']='host'
        for key in ('route-ev','receipt-ev'): record['evidence'][key]=dict(ref='fixture://'+key,sha256=None,kind='host')
        record['evidence']['assessment'].update(kind='independent',file='acceptance.json',sha256=digest(self.run_root/'acceptance.json'))
        for task in record['tasks']:
            task['routing_decision']=ordinary_routing()
            task['resource_preflight']=dict(host='fixture',cpu='1',ram='small',disk='small',evidence='result'); task['resources']=[]
        record['artifact_retention']=dict(run_id='goal-1',manifest_sha256=digest(self.run_root/rc.MANIFEST),consumers=[],quiescent=True)
        save(self.run_root/'record.json',record)
        req=dict(schema='company-native-storage-request/v1',roots=[dict(path=str(self.run_root),kind='company-run',run_id='goal-1',owner='B')],sejong_home=str(self.home),record='record.json',expect_manifest_sha256=digest(self.run_root/rc.MANIFEST))
        return save(self.root/'storage.json',req)

    def apply(self, path):
        plan=self.cli('storage','plan','--request',path)
        p=save(self.root/'plan.json',plan)
        return self.cli('storage','apply','--plan',p,'--expect-plan-sha256',digest(p))

    def test_enroll_before_any_supported_write(self):
        result=self.enroll()
        self.assertEqual(result['status'],'enrolled')
        self.assertTrue(result['readback_verified'])
        self.assertEqual(result['sejong_home'],str(self.home))
        self.assertEqual(set(x.name for x in self.run_root.iterdir()),{rc.MANIFEST,rc.LOCK})
        binding=json.loads(hook.binding_path(self.home,'fixture-session').read_bytes())
        self.assertEqual((binding['run'],binding['record'],binding['owner'],binding['repo_root']),(str(self.run_root),'record.json','B',str(self.cwd)))
        self.assertEqual(self.enroll()['status'],'enrolled')

    def test_missing_identity_or_legacy_contents_never_enroll(self):
        for key,value in [('session_id',''),('cwd','relative'),('host','invented'),('identity_evidence',None)]:
            with self.subTest(key=key):
                old=self.enrollment[key]; self.enrollment[key]=value
                self.enroll(expected=2); self.enrollment[key]=old
                self.assertFalse((self.run_root/rc.MANIFEST).exists())
        (self.run_root/'old.txt').write_text('required historical content')
        self.enroll(expected=1)
        self.assertFalse((self.run_root/rc.MANIFEST).exists())

    def test_home_resolution_and_callback_override_agree(self):
        self.enrollment['host']='codex_stop'
        save(self.identity,dict(host='codex_stop',session_id='fixture-session',cwd=str(self.cwd)))
        self.enrollment['identity_evidence']=pin(self.identity)
        self.enroll(expected=1)
        env={**self.env,'SEJONG_HOME':str(self.home)}
        save(self.enroll_path,self.enrollment)
        self.assertEqual(self.cli('storage','enroll','--request',self.enroll_path,env=env)['status'],'enrolled')

    def test_rebind_active_prior_and_cas_fail_closed(self):
        self.enroll()
        original=hook.binding_path(self.home,'fixture-session').read_bytes()
        self.run_root=self.home/'runs/other';self.run_root.mkdir();self.enrollment.update(run=str(self.run_root),run_id='other',expect_session_binding_sha256=rc.sha(original))
        self.enroll(expected=1)
        self.assertEqual(hook.binding_path(self.home,'fixture-session').read_bytes(),original)

    def test_creation_reservations_and_freeze_do_not_snapshot_live_output(self):
        self.enroll(); a=[self.artifact('raw','recreatable'),self.artifact('unknown','unknown')]
        self.classify(a)
        manifest=json.loads((self.run_root/rc.MANIFEST).read_bytes())
        self.assertEqual(manifest['disposable'],[])
        (self.run_root/'raw').write_text('first');(self.run_root/'raw').write_text('closed')
        (self.run_root/'unknown').write_text('retain unknown')
        self.classify(a,'freeze')
        m=json.loads((self.run_root/rc.MANIFEST).read_bytes())
        self.assertEqual([x['path'] for x in m['disposable']],['raw'])
        self.assertEqual(m['disposable'][0]['sha256'],digest(self.run_root/'raw'))
        self.assertNotIn('unknown',[x['path'] for x in m['disposable']])

    def test_required_originals_promote_before_acceptance(self):
        self.enroll(); a=self.artifact('raw-qa','recreatable'); self.classify([a])
        (self.run_root/'raw-qa').write_bytes(b'original failure QA bytes')
        a.update(**{'class':'preserve'},regeneration=None)
        self.classify([a]);self.classify([a],'freeze')
        m=json.loads((self.run_root/rc.MANIFEST).read_bytes());self.assertEqual(m['disposable'],[])
        self.assertEqual(m['preserve'][0]['sha256'],digest(self.run_root/'raw-qa'))
        self.classify([self.artifact('raw-qa','recreatable')],expected=1)
        self.classify([self.artifact('record.json')],expected=2)

    def test_strict_classification_and_interrupted_reservation(self):
        self.enroll(); a=self.artifact('raw','recreatable');self.classify([a]);self.classify([a],'freeze',expected=1)
        for bad in [{**a,'surprise':True},{**a,'owner':''},{**a,'consumers':['undeclared']},{**a,'regeneration':None},{**a,'path':'../escape'}]:
            self.classify([bad],expected=2)
        self.classify([a,a],expected=2)
        self.assertFalse((self.run_root/'raw').exists())

    def test_closeout_distinguishes_all_five_statuses(self):
        self.assertEqual(self.close(False)['status'],'not_enrolled')
        self.enroll();unknown=self.close();self.assertEqual(unknown['status'],'unknown');self.assertIsNone(unknown['removed_files'])
        hook.dispatch(dict(hook_event_name='Stop',session_id='fixture-session',cwd=str(self.cwd)),self.home)
        skipped=self.close();self.assertEqual(skipped['status'],'skipped');self.assertEqual(skipped['removed_files'],0)

    def test_closeout_receipt_provenance_reappearance_and_nulls(self):
        path=self.accepted();self.apply(path)
        result=self.close();self.assertEqual(result['status'],'removed');self.assertEqual((result['removed_files'],result['removed_logical_bytes']),(1,15));self.assertTrue(result['readback_verified'])
        before=tree(self.run_root);self.close();self.assertEqual(tree(self.run_root),before)
        (self.run_root/'scratch/raw').write_text('replacement')
        blocked=self.close(expected=1);self.assertEqual(blocked['status'],'blocked');self.assertIn('reappeared',blocked['reason'])

    def test_empty_completed_is_no_disposable(self):
        self.apply(self.accepted(False));r=self.close()
        self.assertEqual((r['status'],r['reason'],r['removed_files']),('skipped','no_disposable',0))

    def test_trigger_is_host_specific_and_never_acceptance(self):
        self.enroll()
        trigger=save(self.root/'trigger.json',dict(mode='automatic',host='hermes',event='turn-end',session_id='fixture-session',cwd=str(self.cwd)))
        r=self.close(trigger=pin(trigger));self.assertEqual((r['status'],r['reason']),('skipped','unsupported_automatic_trigger'))
        self.assertFalse((self.run_root/rc.RECEIPT).exists())

    def test_stop_native_and_direct_complete_share_source_owner_denials(self):
        self.enrollment['host']='codex_stop'
        save(self.identity,dict(host='codex_stop',session_id='fixture-session',cwd=str(self.cwd)))
        self.enrollment['identity_evidence']=pin(self.identity);self.env['SEJONG_HOME']=str(self.home)
        path=self.accepted();(self.run_root/'.git').write_text('gitdir: protected')
        plan=self.cli('storage','plan','--request',path,expected=1);self.assertTrue(plan['blockers'])
        out=io.StringIO()
        with contextlib.redirect_stdout(out):code=rc.main(['complete','--run',str(self.run_root),'--sejong-home',str(self.home),'--record','record.json','--expect-manifest-sha256',digest(self.run_root/rc.MANIFEST)])
        self.assertEqual(code,1);self.assertIn('source',out.getvalue())
        result=hook.dispatch(dict(hook_event_name='Stop',session_id='fixture-session',cwd=str(self.cwd)),self.home)
        self.assertEqual(result['status'],'blocked');self.assertTrue((self.run_root/'scratch/raw').exists())

    def test_checked_launch_enrolled_reserves_before_one_fake_start(self):
        import routing_launch
        from types import SimpleNamespace
        self.enroll()
        save(self.run_root/'record.json',dict(goal=dict(id='goal-1',current_owner='B',status='active'),tasks=[]))
        decision=save(self.root/'decision',dict(binding=dict(planned=True,parent_task=None,spec_sha256=rc.sha(b'x'))))
        args=['--enrollment-request',str(self.enroll_path),'--expect-enrollment-sha256',digest(self.enroll_path),'--decision',str(decision),'--record',str(self.run_root/'record.json'),'--receipt',str(self.run_root/'launch-receipt'),'--result',str(self.run_root/'result'),'--from','B','--spec','x','--worktree','current']
        checked=dict(ok=True,label='real',errors=[],receipt=dict(selected=dict(route='codex',model='fixture',effort='high')))
        response=SimpleNamespace(returncode=0,stdout=json.dumps(dict(ok=True,result=dict(taskId='fixture-task',dispatchId='fixture-dispatch',launch=dict(effective=dict(agent='codex',model='fixture',effort='high'))))),stderr='')
        def start(*a,**k):
            manifest=json.loads((self.run_root/rc.MANIFEST).read_bytes())
            self.assertTrue({'result','launch-receipt'} <= set(manifest['creation_contract']))
            self.assertNotIn('result.lock', manifest['creation_contract'])
            self.assertFalse((self.run_root/'result.lock').exists())
            self.assertEqual(manifest['coordination']['lock_identity'][:2], [os.stat(self.run_root/rc.LOCK).st_dev, os.stat(self.run_root/rc.LOCK).st_ino])
            self.assertEqual(manifest['disposable'],[])
            self.assertTrue((self.run_root/'launch-receipt').exists())
            return response
        with contextlib.redirect_stdout(io.StringIO()),patch('routing_launch.shutil.which',return_value='/fake/orca'),patch('routing_launch.check_routing',return_value=checked),patch('routing_launch.subprocess.run',side_effect=start) as host:
            self.assertEqual(routing_launch.main(args),0);self.assertEqual(host.call_count,1)
            self.assertEqual(routing_launch.main(args),1);self.assertEqual(host.call_count,1)

    def test_freeze_open_writer_and_reservation_parent_link_block(self):
        self.enroll();a=self.artifact('raw','recreatable');self.classify([a]);(self.run_root/'raw').write_text('not yet closed')
        with (self.run_root/'raw').open('rb'):
            self.classify([a],'freeze',expected=1)
        outside=self.root/'outside';outside.mkdir();(self.run_root/'linked').symlink_to(outside,target_is_directory=True)
        self.classify([self.artifact('linked/new','recreatable')],expected=1)
        self.assertFalse((outside/'new').exists())

    def test_enrollment_gate_before_result_or_measurement_writes(self):
        import routing_launch
        out=io.StringIO()
        args=['--decision',str(self.root/'decision'),'--record',str(self.run_root/'record.json'),'--receipt',str(self.run_root/'launch-receipt'),'--result',str(self.run_root/'result'),'--from','B','--spec','x','--worktree','current']
        with contextlib.redirect_stdout(out),patch('routing_launch.subprocess.run') as host:
            self.assertEqual(routing_launch.main(args),1);host.assert_not_called()
        self.assertFalse((self.run_root/'result.lock').exists());self.assertFalse((self.run_root/'result').exists())


class MaintenanceStorageTests(NativeCase):
    def legacy_fixture(self):
        import native_maintenance as maintenance
        home=self.root/'sejong';root=home/'runs/old';root.mkdir(parents=True)
        (root/rc.LOCK).touch(mode=0o600)  # existing legacy coordination, not APPLY adoption
        old=save(root/'old-status.json',dict(status='advice-complete'))
        target=root/'generated';target.write_text('fixture disposable')
        proof=save(self.root/'proof.json',dict(fixture=True,disposition='REMOVE',reason='synthetic exact regeneration proof'))
        consumers=save(self.root/'consumers.json',dict(quiescent=True,consumers=[]))
        backup=self.root/'old-status-original.json';backup.write_bytes(old.read_bytes())
        recovery=save(self.root/'recovery.json',dict(copies=[dict(original=str(old),copy=pin(backup))]))
        fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
        try: binding=rc.snapshot_file(fd,'generated'); preserved=rc.snapshot_file(fd,'old-status.json')
        finally:os.close(fd)
        st=target.stat()
        request=dict(schema='company-native-storage-maintenance-request/v1',operation_id='fixture-op',owner='fixture-owner',sejong_home=str(home),root=str(root),targets=[dict(**binding,uid=st.st_uid,mode=stat.S_IMODE(st.st_mode),origin='fixture generation',unnecessary_proof=pin(proof),remaining_consumers=[])],preserve=[preserved],historical_metadata=[dict(path=name,sha256=None,identity=None) for name in sorted(rc.RESERVED-{rc.LOCK})],classification_evidence=pin(proof),consumer_evidence=pin(consumers),preservation_evidence=pin(recovery))
        request_path=save(self.root/'request.json',request)
        plan=self.cli('storage','maintenance-plan','--request',request_path)
        plan_path=save(self.root/'plan.json',plan)
        import subprocess
        marker=PACKAGE/'.agent-company-skill.json'
        revision=json.loads(marker.read_bytes()).get('agent_company_commit') if marker.exists() else subprocess.check_output(['git','-C',str(PACKAGE.parents[1]),'rev-parse','HEAD'],text=True).strip()
        if revision is None and marker.exists():
            revision=next(v for v in json.loads(marker.read_bytes()).values() if isinstance(v,str) and len(v)==40)
        candidate=save(self.root/'candidate.json',dict(revision=revision,package_sha256=maintenance.package_fingerprint()))
        auth=dict(schema='company-native-storage-maintenance-authorization/v1',operation_id='fixture-op',owner='fixture-owner',host=plan['host'],plan_sha256=digest(plan_path),approved_by='fixture-owner',approved_at='2020-01-01T00:00:00+00:00',valid_until='2100-01-01T00:00:00+00:00',scope=['generated'],authority_evidence=pin(proof))
        review=dict(schema='company-native-storage-maintenance-review/v1',operation_id='fixture-op',owner='fixture-owner',host=plan['host'],plan_sha256=digest(plan_path),assessor='fixture-independent',executor='fixture-owner',candidate=dict(revision=revision,dirty_manifest=pin(candidate)),verdict='approved',reviewed_at='2020-01-01T00:00:00+00:00',valid_until='2100-01-01T00:00:00+00:00',inventory_evidence=pin(proof),preservation_evidence=pin(recovery),consent_evidence=pin(proof),prior_denial_resolution=None)
        a=save(self.root/'authorization.json',auth);r=save(self.root/'review.json',review)
        return root,request_path,plan_path,a,r,auth,review

    def invoke_apply(self,p,a,r,expected=0):
        return self.cli('storage','maintenance-apply','--plan',p,'--expect-plan-sha256',digest(p),'--authorization',a,'--review',r,expected=expected)

    def test_apply_uses_common_engine_and_verifies_external_receipts(self):
        import native_maintenance as maintenance
        root,request,p,a,r,auth,review=self.legacy_fixture()
        old=(root/'old-status.json').read_bytes(); identity=rc.signature((root/'old-status.json').stat())
        with patch('run_completion.unlink_exact',wraps=rc.unlink_exact) as engine:
            result=maintenance.apply(p,digest(p),a,r)
        self.assertEqual(engine.call_count,1)
        self.assertEqual(result['status'],'completed',result);self.assertTrue(result['readback_verified'])
        self.assertFalse((root/'generated').exists());self.assertEqual((root/'old-status.json').read_bytes(),old)
        self.assertEqual(rc.signature((root/'old-status.json').stat()),identity)
        self.assertEqual(set(x.name for x in root.iterdir()),{'old-status.json',rc.LOCK})
        receipt=json.loads(Path(result['receipt']['path']).read_bytes());self.assertEqual(receipt['removed'],result['removed'])
        self.invoke_apply(p,a,r,expected=1)
        self.assertEqual(json.loads(Path(result['receipt']['path']).read_bytes()),receipt)

    def test_missing_stale_self_approval_or_prior_denial_blocks(self):
        root,request,p,a,r,auth,review=self.legacy_fixture();before=tree(root)
        for key,value in [('plan_sha256','0'*64),('host','wrong-host'),('approved_by','another'),('valid_until','2001-01-01T00:00:00+00:00'),('scope',[])]:
            old=auth[key];auth[key]=value;save(a,auth);self.invoke_apply(p,a,r,expected=1);auth[key]=old;save(a,auth)
        for key,value in [('assessor','fixture-owner'),('verdict','pending'),('prior_denial_resolution',{'denial':pin(self.root/'proof.json'),'resolution':{'path':str(self.root/'absent'),'sha256':'0'*64}})]:
            old=review[key];review[key]=value;save(r,review);self.invoke_apply(p,a,r,expected=1);review[key]=old;save(r,review)
        self.assertEqual(tree(root),before)

    def test_guard_union_exact_scope_and_historical_evidence(self):
        root,request,p,a,r,auth,review=self.legacy_fixture();before=(root/'generated').read_bytes()
        for name in ('.git','.pin'):
            (root/name).write_text('protected')
            self.invoke_apply(p,a,r,expected=1);(root/name).unlink()
        (root/'generated').chmod(0o666)
        self.invoke_apply(p,a,r,expected=1)
        self.assertEqual((root/'generated').read_bytes(),before)

    def test_missing_authority_never_registers_historical_run(self):
        home=self.root/'sejong';root=home/'runs/old';root.mkdir(parents=True)
        old=save(root/'old-status.json',dict(status='advice-complete'))
        target=root/'generated';target.write_text('fixture disposable')
        evidence=save(self.root/'evidence.json',dict(fixture=True))
        fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
        try: binding=rc.snapshot_file(fd,'generated'); preserved=rc.snapshot_file(fd,'old-status.json')
        finally:os.close(fd)
        st=target.stat()
        request=dict(schema='company-native-storage-maintenance-request/v1',operation_id='fixture-op',owner='fixture-owner',sejong_home=str(home),root=str(root),targets=[dict(**binding,uid=st.st_uid,mode=stat.S_IMODE(st.st_mode),origin='fixture generation',unnecessary_proof=pin(evidence),remaining_consumers=[])],preserve=[preserved],historical_metadata=[dict(path=name,sha256=None,identity=None) for name in sorted(rc.RESERVED-{rc.LOCK})],classification_evidence=pin(evidence),consumer_evidence=pin(evidence),preservation_evidence=pin(evidence))
        before=tree(root)
        plan=self.cli('storage','maintenance-plan','--request',save(self.root/'request.json',request))
        self.assertTrue(plan['ready']);self.assertFalse(plan['apply_authorized']);self.assertEqual(tree(root),before)
        p=save(self.root/'plan.json',plan)
        self.cli('storage','maintenance-apply','--plan',p,'--expect-plan-sha256',digest(p),'--authorization',self.root/'missing','--review',self.root/'missing-review',expected=1)
        self.assertEqual(tree(root),before);self.assertFalse((root/rc.MANIFEST).exists())
