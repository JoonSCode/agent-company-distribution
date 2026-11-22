"""Retained --layout legacy geometry, identity, paging and cache contracts.

Synthetic in-memory views are layout probes, never staffing/execution evidence.
Original reader/checker negative suites remain separate and unchanged.
Default wide output and real keys are covered by test_status_tui_wide.
"""
from __future__ import annotations
import copy
import hashlib
import json
import os
from pathlib import Path
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import status_tui as tui
import status_tui_graph as graph
import status_tui_data as data
from test_status_tui import child_env
from test_status_tui_data import fixture

SIZES = ((98,12),(98,27),(80,12),(120,20),(80,24),(120,40),(48,12),(20,4),(1,1))


class GraphTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        fixture(self.root,count=7)
        self.base = data.load_snapshot(self.root/'view.json')

    def snapshot(self, needs):
        snap = copy.deepcopy(self.base)
        snap['tasks'] = snap['tasks'][:len(needs)]
        for i,(task,prerequisites) in enumerate(zip(snap['tasks'],needs)):
            task.update(id='t'+str(i+1), needs=['t'+str(n) for n in prerequisites],
                        title='합성 '+str(i+1)+' 작업 지도', assigned_model='gpt-5.1-codex-max', model_basis='assigned')
        return snap

    def plan(self,snap,w=120,h=20):
        return graph.layout(snap,w-1,h-1)

    def frames(self,snap,w=120,h=20,**kwargs):
        return [tui._legacy_frame(snap,w,h,page=i,**kwargs) for i in range(tui._legacy_page_count(snap,w,h))]

    def assert_actual_geometry(self,snap,w,h):
        plan = self.plan(snap,w,h)
        rendered = self.frames(snap,w,h)
        for index,page in enumerate(plan['pages']):
            if page['kind'] != 'graph': continue
            body = graph.draw_page(snap,plan,index,w-1)
            frame = rendered[index].splitlines()
            self.assertEqual(frame[2:2+len(body)],body)
            positions = {node['id']:node for node in page['nodes']}
            # Source and target border + all three gutter cells, NOT just an arrow substring.
            for source,target in page['edges']:
                a,b = positions[source],positions[target]
                self.assertLess(a['x'],b['x'])
                y0,y1 = a['y']+4,b['y']+4
                def at(x,y):
                    used=0
                    for c in body[y]:
                        if used==x:return c
                        used+=graph.cells(c)
                    self.fail('missing cell '+str((x,y)))
                self.assertEqual(at(a['x']+a['width']-1,y0),'├')
                self.assertEqual(at(b['x']-1,y1),'▶')
                self.assertEqual(at(b['x'],y1),'┤')
                for y in range(min(y0,y1)+1,max(y0,y1)):
                    self.assertIn(at(a['x']+a['width']+1,y),'│├┤┬┴┼')
                for identity in (source,target):
                    self.assertIn(plan['refs'][identity],rendered[index])

    def test_chain_actual_boundary_connections_at_short_normal_widths(self):
        snap=self.snapshot([[],[1]])
        for w,h in ((98,12),(80,12),(120,20),(98,27)):
            self.assert_actual_geometry(snap,w,h)
            page=self.plan(snap,w,h)['pages'][0]
            self.assertEqual([n['id'] for n in page['nodes']],['t1','t2'])
            self.assertEqual(page['edges'],[('t1','t2')])

    def test_fork_has_two_real_arrowheads_and_shared_predecessor(self):
        snap=self.snapshot([[],[1],[1]])
        self.assert_actual_geometry(snap,120,20)
        page=self.plan(snap)['pages'][0]
        self.assertEqual(set(map(tuple,page['edges'])),{('t1','t2'),('t1','t3')})
        self.assertEqual(self.frames(snap)[0].count('▶'),2)
        self.assertIn('┤',self.frames(snap)[0])

    def test_fanin_has_two_sources_and_one_consumer(self):
        snap=self.snapshot([[],[],[1,2]])
        self.assert_actual_geometry(snap,120,20)
        page=self.plan(snap)['pages'][0]
        self.assertEqual(set(map(tuple,page['edges'])),{('t1','t3'),('t2','t3')})
        positions={n['id']:n for n in page['nodes']}
        self.assertEqual(positions['t1']['x'],positions['t2']['x'])
        self.assertGreater(positions['t3']['x'],positions['t1']['x'])
        self.assertEqual(self.frames(snap)[0].count('▶'),1)  # shared inlet, two source paths

    def test_diamond_cross_team_and_disconnected_reachability(self):
        snap=self.snapshot([[],[1],[1],[2,3],[],[4],[4,6]])
        snap['tasks'][4]['team_id']=None
        for w,h in ((98,12),(120,20),(48,12),(98,27)):
            plan=self.plan(snap,w,h)
            self.assertEqual(set(plan['node_pages']),{t['id'] for t in snap['tasks']})
            expected={(p,t['id']) for t in snap['tasks'] for p in t['needs']}
            self.assertEqual(set(plan['edge_pages']),expected)
            frames=self.frames(snap,w,h)
            for task in snap['tasks']:
                self.assertIn(plan['refs'][task['id']],frames[plan['node_pages'][task['id']]-1])
            for edge,page in plan['edge_pages'].items():
                a,b=edge
                self.assertEqual(plan['pages'][page-1]['kind'],'portal')
                self.assertIn(plan['refs'][a]+' ['+str(plan['node_pages'][a])+']',frames[page-1])
                self.assertIn(plan['refs'][b]+' ['+str(plan['node_pages'][b])+']',frames[page-1])
                self.assertIn('ID: '+a,frames[page-1]);self.assertIn(' -> '+b,frames[page-1])
            self.assertTrue(any('소속 미확인' in f for f in frames))
            self.assert_actual_geometry(snap,w,h)

    def test_disconnected_nodes_have_no_decorative_edge(self):
        snap=self.snapshot([[],[],[]])
        plan=self.plan(snap)
        self.assertEqual(plan['edges'],[])
        self.assertTrue(all(not p['edges'] for p in plan['pages']))
        self.assertNotIn('▶','\n'.join(self.frames(snap)))
        self.assertIn('독립 여부 미확인',self.frames(snap)[0])

    def test_page_wrap_and_status_layout_stability(self):
        snap=self.snapshot([[],[1],[1],[2,3],[],[4],[4,6]])
        for w,h in ((98,12),(120,20),(48,12)):
            before=self.plan(snap,w,h)
            for state in graph.STATES:
                changed=copy.deepcopy(snap)
                for task in changed['tasks']:task['state']=state
                self.assertEqual(before,self.plan(changed,w,h))
            count=tui._legacy_page_count(snap,w,h)
            self.assertEqual(tui._legacy_frame(snap,w,h,page=count),tui._legacy_frame(snap,w,h,page=0))
            self.assertIn('page:1/',tui._legacy_frame(snap,w,h,page=count*4))

    def test_all_sizes_all_pages_cjk_and_long_fields_bounded(self):
        snap=self.snapshot([[],[1],[1],[2,3],[],[4],[4,6]])
        for task in snap['tasks']:
            task.update(title='한글\u0301中文界'*40,classification='structured_data',assigned_model='model-'+('界e\u0301'*40))
            task['specialist']={'status':'assigned','id':'custom-native-'+('界'*50)}
        for w,h in SIZES:
            for mode in tui.MODES:
                for page in range(tui._legacy_page_count(snap,w,h,mode)):
                    frame=tui._legacy_frame(snap,w,h,mode,page)
                    self.assertLessEqual(len(frame.splitlines()),max(1,h-1),(w,h,mode,page))
                    for line in frame.splitlines():self.assertLessEqual(graph.cells(line),max(1,w-1))
        for w in (80,98,120):
            frame=tui._legacy_frame(snap,w,12)
            for text in ('구조화 데이터','할당:','전문가명 미확인:'):
                self.assertIn(text,frame)
            self.assertIn('~',frame)

    def test_long_same_prefix_ids_have_stable_refs_and_reachable_exact_mapping(self):
        snap=self.snapshot([[],[1]])
        first='shared-'+('long-prefix-'*12)+'a'
        second='shared-'+('long-prefix-'*12)+'b'
        snap['tasks'][0]['id']=first
        snap['tasks'][1].update(id=second,needs=[first])
        plan=self.plan(snap,80,12)
        self.assertEqual(plan['refs'],{first:'@1',second:'@2'})
        for identity in (first,second):
            pages=[p for p in plan['pages'] if p['kind']=='identity' and p['task']==identity]
            self.assertTrue(pages)
            self.assertEqual(''.join(line for p in pages for line in p['lines'][1:]),identity)
        frame=tui._legacy_frame(snap,80,12)
        self.assertIn('@1 ID~',frame);self.assertIn('@2 ID~',frame)
        self.assertIn('├──▶┤',frame)

    def test_controls_are_replaced_in_every_displayed_source_field(self):
        snap=self.snapshot([[],[1]])
        attack='safe\x1b[2J\n\r\x9b31m\u202eevil\u2066end'
        for task in snap['tasks']:
            task.update(title=attack,assigned_model=attack)
            task['specialist']={'status':'assigned','id':attack}
        snap['organization']['teams'][0]['label']=attack
        for frame in self.frames(snap,120,20):
            for c in ('\x1b','\n\r','\x9b','\u202e','\u2066'):self.assertNotIn(c,frame)
        self.assertEqual(graph.clean(attack),'safe?[2J???31m?evil?end')

    def test_exact_korean_states_and_checker_priority_not_rewritten(self):
        snap=self.snapshot([[],[1]])
        task=snap['tasks'][1]
        for state,label in graph.STATES.items():
            task['state']=state
            self.assertIn(label,tui._legacy_frame(snap,98,12))
        self.assertEqual(data._state(task)[0],'ACC')
        task['errors']=['task error']
        task['stages']['technical']['badge_kind']='error'
        self.assertEqual(data._state(task)[0],'FAIL')
        task['stages']['technical']['badge_kind']='pending'
        self.assertEqual(data._state(task)[0],'ERR')
        task['errors']=[]
        task['stages']['technical']['earned_success']=False
        self.assertEqual(data._state(task)[0],'SUB')
        task['stages']['execution'].update(earned_success=False,state='live')
        self.assertEqual(data._state(task)[0],'?')
        self.assertNotIn('미시작',tui._legacy_frame(snap,98,12))
        for state in ('ACC','SUB','ERR'):
            task['state']=state;snap['tasks'][0]['state']='?'
            self.assertIn(graph.STATES[state],tui._legacy_frame(snap,98,12))

    def test_goal_pending_error_pass_is_separate_from_all_tasks_passed(self):
        snap=self.snapshot([[],[1]])
        for kind,earned,label in [('pending',False,'확인 대기'),('error',False,'오류'),('success',True,'기록상 통과')]:
            snap['overall_goal_acceptance'].update(badge_kind=kind,earned_success=earned)
            frame=tui._legacy_frame(snap,98,12)
            self.assertIn('전체 목표: '+label,frame)
            self.assertIn('사용자 확인: 미관측',frame)
            self.assertIn('작업 검토 통과',frame)
            self.assertNotIn('사용자 승인',frame)

    def test_all_classifications_are_fixed_translations_not_assignments(self):
        snap=self.snapshot([[]]);task=snap['tasks'][0]
        for code,label in graph.CLASSES.items():
            task['classification']=code
            self.assertIn(label,tui._legacy_frame(snap,98,12))
            self.assertEqual(graph.specialist_label(task),'전문가 미확인')
        task['classification']=None
        self.assertIn('분류 미확인',tui._legacy_frame(snap,98,12))

    def test_assigned_planned_unknown_opaque_and_custom_models(self):
        snap=self.snapshot([[]]);task=snap['tasks'][0]
        for basis,identity,label in [('assigned','gpt-5.1','할당: gpt-5.1'),('planned','custom','계획: custom'),
                                     ('unknown',None,'모델 미확인'),('assigned','m1','모델명 미확인 · 할당 ID:m1'),
                                     ('assigned','x7','할당: x7')]:
            task.update(model_basis=basis,assigned_model=identity)
            self.assertIn(label,tui._legacy_frame(snap,98,12))
        task.update(model_basis='unknown',assigned_model='observed-only')
        self.assertEqual(graph.model_label(task),'모델 미확인')

    def test_specialist_localization_requires_exact_proven_assigned_id(self):
        snap=self.snapshot([[]]);task=snap['tasks'][0]
        for identity,label in graph.SPECIALISTS.items():
            task['specialist']={'status':'assigned','id':identity}
            self.assertIn(label,tui._legacy_frame(snap,98,12))
            for status in ('none','unknown'):
                task['specialist']={'status':status,'id':identity}
                self.assertNotIn(label,tui._legacy_frame(snap,98,12))
                self.assertIn('전문가 없음' if status=='none' else '전문가 미확인',tui._legacy_frame(snap,98,12))
        task['specialist']={'status':'assigned','id':'custom-agent'}
        self.assertIn('전문가명 미확인: custom-agent',tui._legacy_frame(snap,98,12))
        task['specialist']={'status':'assigned','id':'agent-company-development-extra'}
        self.assertNotEqual(graph.specialist_label(task),'개발 전문가')

    def test_partial_unknown_and_known_empty_do_not_invent_independence(self):
        snap=self.snapshot([[]])
        for coverage,label in [('partial','연결 일부만 기록'),('unknown','연결 정보 미확인')]:
            snap['dependency_coverage']=coverage
            frame=tui._legacy_frame(snap,98,12)
            self.assertIn(label,frame);self.assertIn('독립 여부 미확인',frame)
            self.assertNotIn('실행 가능',frame)
        snap['organization']=None;snap['tasks'][0]['team_id']=None
        self.assertIn('조직 미기록',tui._legacy_frame(snap,98,12))

    def test_ascii_translates_state_absence_unknown_and_graph_not_question_marks(self):
        snap=self.snapshot([[],[1]])
        for state in graph.STATES:
            snap['tasks'][0]['state']=state
            snap['tasks'][0]['classification']='structured_data'
            frame=tui._legacy_frame(snap,80,12,ascii=True)
            self.assertTrue(frame.isascii());self.assertIn(graph.EN_STATES[state],frame)
            self.assertIn('data',frame);self.assertIn('+-->+',frame)
            self.assertIn('Specialist unknown',frame)
        snap['tasks'][1]['specialist']={'status':'none','id':None}
        self.assertIn('Specialist none',tui._legacy_frame(snap,80,12,ascii=True))

    def test_no_color_env_and_mandatory_text_never_faint(self):
        snap=self.snapshot([[],[1]])
        with patch.dict(os.environ,{'NO_COLOR':'1'}):
            self.assertNotIn('\x1b',tui._legacy_frame(snap,98,12,color=True))
        with patch.dict(os.environ,{},clear=True):
            frame=tui._legacy_frame(snap,98,12,color=True)
            self.assertIn('\x1b[',frame);self.assertNotIn('\x1b[2m',frame)
            plain=re.sub(r'\x1b\[[0-9;]*m','',frame)
            self.assertEqual(plain,tui._legacy_frame(snap,98,12))

    def test_semantic_colors_are_per_node_not_title_model_or_neighbor_words(self):
        def styled_cells(line):
            result, x, style, start = {}, 0, None, 0
            for match in re.finditer(r'\x1b\[([0-9;]*)m', line):
                for char in line[start:match.start()]:
                    size = graph.cells(char)
                    for offset in range(size): result[x+offset] = style
                    x += size
                style = None if match[1] in ('', '0') else match[1]
                start = match.end()
            for char in line[start:]:
                size = graph.cells(char)
                for offset in range(size): result[x+offset] = style
                x += size
            return result
        for w,h in ((98,12),(98,27),(80,12),(120,20),(120,40)):
            for states in [('ACC','WAIT'),('ERR','ACC'),('ACC','ACC'),('FAIL','SUB'),('?','ACC')]:
                snap=self.snapshot([[],[1]])
                for task,state in zip(snap['tasks'],states):
                    task.update(state=state,title='오류 대기 분석\u0301',assigned_model='오류-대기-model')
                plan=self.plan(snap,w,h)
                with patch.dict(os.environ,{},clear=True):
                    colored=tui._legacy_frame(snap,w,h,color=True)
                plain=tui._legacy_frame(snap,w,h)
                self.assertEqual(re.sub(r'\x1b\[[0-9;]*m','',colored),plain)
                lines=colored.splitlines()
                for node,state in zip(plan['pages'][0]['nodes'],states):
                    x,y=node['x']+2,node['y']+2+2
                    title=styled_cells(lines[y]);status=styled_cells(lines[y+1])
                    for cell in range(x,x+graph.cells(graph.STATES[state])):
                        self.assertEqual(status[cell],graph.STATE_STYLES[state],(w,h,state,cell))
                    self.assertEqual(title[x],'1;39')
                    self.assertNotIn('1;31',set(title.values()))
                    model_row=y+2 if not plan['pages'][0]['split'] else y+3
                    self.assertNotIn('1;31',set(styled_cells(lines[model_row]).values()))
                self.assertNotIn('\x1b[2m',colored)
                with patch.dict(os.environ,{'NO_COLOR':''}):
                    self.assertEqual(tui._legacy_frame(snap,w,h,color=True),plain)
                ascii_frame=tui._legacy_frame(snap,w,h,color=True,ascii=True)
                self.assertNotIn('\x1b',ascii_frame);self.assertTrue(ascii_frame.isascii())

    def test_compact_directory_packed_slices_preserve_geometry_and_primary_pages(self):
        snap=self.snapshot([[],[1],[1],[2,3],[4],[],[5]])
        for w,h,limit in [(120,40,4),(98,27,8),(80,24,8),(98,12,13),(48,12,13)]:
            plan=self.plan(snap,w,h);frames=self.frames(snap,w,h)
            self.assertLessEqual(len(frames),limit,(w,h))
            self.assertEqual(set(plan['node_pages']),{t['id'] for t in snap['tasks']})
            self.assertEqual(set(plan['edge_pages']),set(graph.known_edges(snap)))
            for index,page in enumerate(plan['pages']):
                ids=[n['id'] for n in page['nodes']]
                self.assertEqual(len(ids),len(set(ids)),'packed duplicate node would redirect edges')
                if page['kind']=='graph':
                    self.assertLessEqual(max(n['y']+n['height']+1 for n in page['nodes']),plan['room'])
                for identity,primary in plan['node_pages'].items():
                    self.assertIn(plan['refs'][identity],frames[primary-1])
            for (a,b),number in plan['edge_pages'].items():
                frame=frames[number-1]
                self.assertIn(plan['refs'][a]+' ['+str(plan['node_pages'][a])+']',frame)
                self.assertIn(plan['refs'][b]+' ['+str(plan['node_pages'][b])+']',frame)
                self.assertIn('ID: '+a,frame);self.assertIn(' -> '+b,frame)
            self.assert_actual_geometry(snap,w,h)
            if h>=24:self.assertTrue(any(len(p['edges'])>1 for p in plan['pages'] if p['kind']=='portal'))

    def test_tiny_is_one_enlarge_only_page_with_exit_not_phantom_navigation(self):
        snap=self.snapshot([[],[1],[1],[2,3],[4],[],[5]])
        for w in (1,8,20,48,98):
            for h in range(1,7):
                for mode in tui.MODES:
                    self.assertEqual(tui._legacy_page_count(snap,w,h,mode),1)
                    frame=tui._legacy_frame(snap,w,h,mode,page=400)
                    self.assertIn('q',frame.splitlines()[0])
                    self.assertNotIn('n/p',frame);self.assertNotIn('page:',frame)
                    self.assertEqual(frame,tui._legacy_frame(snap,w,h,mode,page=0))
                    self.assertLessEqual(len(frame.splitlines()),max(1,h-1))
                    if w>=20 and h>=3:self.assertIn('확대 필요',frame)
                    for line in frame.splitlines():self.assertLessEqual(graph.cells(line),max(1,w-1))

    def test_portal_boundary_reserves_footer_and_provenance_on_every_page(self):
        snap=self.snapshot([[],[1]])
        snap.update(record_label='synthetic',dependency_coverage='partial')
        for h in (7,8,9):
            plan=self.plan(snap,98,h)
            for mode in ('flow','combined'):
                for index,page in enumerate(plan['pages']):
                    with self.subTest(height=h,mode=mode,page=index):
                        body=graph.draw_page(snap,plan,index,97)
                        self.assertLessEqual(len(body),plan['room'])
                        frame=tui._legacy_frame(snap,98,h,mode,index)
                        for token in ('합성 시연','연결 일부만 기록','실행 관측 없음',
                                      '확대 필요 · n/p 작업/연결 정보'):
                            self.assertIn(token,frame)
                        self.assertLessEqual(len(frame.splitlines()),h-1)
            portals=[(i,p) for i,p in enumerate(plan['pages']) if p['kind']=='portal']
            self.assertTrue(portals)
            collected='\n'.join('\n'.join(graph.draw_page(snap,plan,i,97)) for i,p in portals)
            for token in ('선행 연결 · 실행 순서 관측 아님','ID: t1',' -> t2'):
                self.assertIn(token,collected)
            for i,page in portals:
                body='\n'.join(graph.draw_page(snap,plan,i,97))
                for identity in ('t1','t2'):
                    self.assertIn(plan['refs'][identity]+' ['+str(plan['node_pages'][identity])+']',body)
            for edge,number in plan['edge_pages'].items():
                self.assertIn(edge,plan['pages'][number-1]['edges'])

    def test_boundary_long_ids_keep_reachable_exact_continuations(self):
        snap=self.snapshot([[],[1]])
        ids=['shared-'+('long-prefix-'*12)+suffix for suffix in ('a','b')]
        snap['tasks'][0]['id']=ids[0]
        snap['tasks'][1].update(id=ids[1],needs=[ids[0]])
        for w in (48,80,98,120):
            for h in (7,8,9):
                plan=self.plan(snap,w,h)
                for index,page in enumerate(plan['pages']):
                    self.assertLessEqual(len(graph.draw_page(snap,plan,index,w-1)),plan['room'])
                for identity in ids:
                    pages=[p for p in plan['pages'] if p['kind']=='identity' and p['task']==identity]
                    self.assertEqual(''.join(line for p in pages for line in p['lines'][1:]),identity)
                    self.assertIn(plan['refs'][identity],self.frames(snap,w,h)[plan['node_pages'][identity]-1])
                for edge,number in plan['edge_pages'].items():
                    self.assertIn(edge,plan['pages'][number-1]['edges'])

    def test_last_good_error_precedes_goal_and_keeps_graph(self):
        snap=self.snapshot([[],[1]])
        snap.update(_refresh_error='InputError',_last_good_age=5)
        frame=tui._legacy_frame(snap,98,12)
        self.assertTrue(frame.startswith('ERROR | last-good 5s | 갱신 오류·오래된 화면'))
        self.assertIn('├──▶┤',frame)
        self.assertIn('작업 검토 통과',frame)
        for w,h in ((48,12),(20,4)):
            self.assertTrue(tui._legacy_frame(snap,w,h).startswith('ERROR'))

    def test_pure_renderer_and_json_do_not_mutate_input(self):
        snap=self.snapshot([[],[1],[1]])
        frozen=json.dumps(snap,ensure_ascii=False,sort_keys=True)
        self.frames(snap);tui._legacy_frame(snap,98,12,ascii=True)
        self.assertEqual(json.dumps(snap,ensure_ascii=False,sort_keys=True),frozen)

    def test_cli_ascii_uses_translated_product_renderer_and_no_color(self):
        script=Path(tui.__file__)
        result=subprocess.run([sys.executable,'-B',script,'--manifest',self.root/'view.json','--once',
                               '--width','80','--height','12','--ascii','--no-color','--layout','legacy'],
                              env=child_env(self.root),capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(result.stdout.isascii());self.assertIn('Task review passed',result.stdout)
        self.assertIn('+-->+',result.stdout);self.assertNotIn('\x1b',result.stdout)
        self.assertEqual(result.stdout.rstrip('\n'),tui._legacy_frame(self.base,80,12,ascii=True))

    def test_new_graph_import_ignores_poisoned_managed_cache_without_writes(self):
        scripts=self.root/'managed'
        shutil.copytree(Path(tui.__file__).parent,scripts,ignore=shutil.ignore_patterns('__pycache__','.pytest_cache'))
        source=scripts/'status_tui_graph.py';original=source.read_bytes();stat=source.stat()
        poison=b"raise RuntimeError('GRAPH_MANAGED_POISON')\n"
        source.write_bytes(poison+b'#'*(len(original)-len(poison)))
        os.utime(source,ns=(stat.st_atime_ns,stat.st_mtime_ns))
        cache=scripts/'__pycache__'/('status_tui_graph.'+sys.implementation.cache_tag+'.pyc')
        cache.parent.mkdir()
        py_compile.compile(str(source),cfile=str(cache),doraise=True,invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)
        source.write_bytes(original);os.utime(source,ns=(stat.st_atime_ns,stat.st_mtime_ns))
        before=hashlib.sha256(cache.read_bytes()).hexdigest()
        negative=subprocess.run([sys.executable,'-B','-c','import status_tui_graph'],cwd=scripts,env=child_env(self.root),capture_output=True,text=True,timeout=10)
        self.assertNotEqual(negative.returncode,0);self.assertIn('GRAPH_MANAGED_POISON',negative.stderr)
        result=subprocess.run([sys.executable,'-B',scripts/'status_tui.py','--help'],env=child_env(self.root),capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertNotIn('GRAPH_MANAGED_POISON',result.stderr)
        self.assertEqual(hashlib.sha256(cache.read_bytes()).hexdigest(),before)
        self.assertEqual(list(cache.parent.iterdir()),[cache])


if __name__=='__main__':unittest.main()
