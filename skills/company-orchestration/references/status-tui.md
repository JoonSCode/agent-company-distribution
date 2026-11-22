# 조직·팀별 작업 상주 TUI

`../scripts/status_tui.py`는 지정한 로컬 Orca Run 또는 명시 파일을 여는 Company 진입점이다. stdlib Python 3.13을 사용한다. 조직 회사→팀→lead/member와 Task/Dispatch/needs DAG를 **서로 다른 관계**로 유지한다. 상주와 once 모드는 읽기 전용이다. 아래 명시 `--capture-context`만 새 private planning context 한 파일을 쓴다. 실제 Orca pane은 호출자가 선택한다.

## 실행과 키

```sh
python3.13 -B /path/to/company-orchestration/scripts/status_tui.py --run run_EXACT_ID
python3.13 -B /path/to/company-orchestration/scripts/status_tui.py --run run_EXACT_ID --once --json
python3.13 -B /path/to/company-orchestration/scripts/status_tui.py --record /private/run/record.json --mode combined
python3.13 -B /path/to/company-orchestration/scripts/status_tui.py --record /private/run/record.json --once --json
python3.13 -B /path/to/company-orchestration/scripts/status_tui.py --manifest /private/run/view.json --mode combined
python3.13 -B /path/to/company-orchestration/scripts/status_tui.py --manifest /private/run/view.json --mode org --once --width 80 --height 12
python3.13 -B /path/to/company-orchestration/scripts/status_tui.py --manifest /private/run/view.json --mode flow --once --json
```

* `--run`은 호출자가 지정한 ID로 로컬 Orca의 작업 목록만 읽는다. 시작 당시 선택을 화면이 열린 동안 유지한다. 다른 Run이나 잘못된 작업 관계가 응답에 섞이면 마지막 정상 화면과 갱신 오류를 함께 표시한다. Task 제목, Orca 상태, 명시된 선행 조건만 화면에 사용한다. 부모 Task는 선행 조건과 별도로 원문 보기에서 확인할 수 있다. Orca에서 완료된 작업의 Company 수락과 사용자 확인은 미확인으로 표시한다. 프로그램이 pane을 열거나 기록을 쓰거나 작업을 실행하지 않는다.
* `--record`는 **명시 선택한 기존 Company supplementary record**의 현재 바이트를 읽는다. `--manifest`는 고정 pin을 검증한다. `--run`, `--record`, `--manifest` 중 하나만 선택한다. 선택 `--metadata /private/run/view.json` 또는 `--context /private/view/context.json`은 `--record`와만 사용할 수 있고 서로 배타적이다.
* 기본 combined + `--layout wide`: viewport를 채우는 네 필드 카드지도다. `o` 조직, `f` 흐름, `c` 통합, `n` 다음/`p` 이전 페이지, `q` 종료는 그대로이며 마지막 페이지에서 순환한다. `j/k` 작업 선택, `x` 보조 초점 지도, `w` 넓은 지도, `v` 전체 개요, `t` 팀, `r` 기록 위상 구간, `l` 선택 작업의 이름 있는 정확한 연결, `s` 원본·배정 근거, `Enter` 선택 진입/연결 반대편, `b` 뒤로를 추가한다. `f`를 초점 키로 덮어쓰지 않는다. `--layout focus`는 선택 작업과 실제 이웃만 보여 주며, `--layout legacy`는 이전 작은 slice 표현을 명시 선택하는 호환 경로다. 방향키/마우스는 지원하지 않는다.
* 상주는 caller가 소유한 동일 stdin/stdout PTY에서만 실행한다. TERM=dumb/unknown, 파이프는 거부한다. PTY 소유권은 operator 책임이며 다른 terminal의 권한을 얻는 도구가 아니다.
* `--once`만 비TTY/`--json`/`--width`/`--height` 허용. 기본 snapshot80×12. 상주는 실제 PTY 크기와 SIGWINCH 사용. width/height 양의 정수.
* `--interval` 기본1초, 유한한0.25초 이상. redraw 최대4Hz, unchanged 무재출력, idle 읽기 최대5초 backoff. 오류는5초 backoff, last-good+ERROR+마지막 정상 읽기 age를 표시한다. generated_at은 projection 시각이지 observation freshness가 아니다. 입력이 복구되면 다음 read 때 전체 새 snapshot으로 교체한다. 부분 merge 없음.
* `NO_COLOR` 존재 또는 `--no-color`는 SGR을 출력하지 않는다. `--palette light|dark`는 프로그램 안의 의미색만 선택한다(기본 light). 배경·호스트 테마·폰트는 바꾸지 않는다. cursor/alternate-screen 제어는 여전히 필요하다. `--ascii`는 상태·분류·모델 할당/계획·전문가 없음/미확인을 영어로 표시하고 `+-->/|` 구조선을 사용한다. 사용자가 공급한 비ASCII 제목/ID/팀명만 안전한 `?`로 대체하며, 원문 JSON의 비ASCII는 escape로 접근 가능하다. Unicode 기본 지도는 둥근 경계와 실제 방향 화살촉을 사용한다.
* exit0: 정상 종료/유효 once(체커 불통과가 있어도 snapshot은 유효할 수 있음). exit2: 입력/터미널/인자 오류. 상주 중 invalid candidate는 종료 대신 명시 ERROR와 last-good를 유지한다. q/SIGINT/SIGTERM은 원래 termios 모드와 커서를 복원하고 alternate screen에서 나온다. 강제 SIGKILL/단말 단절 복원은 보장하지 않는다. 기존 cbreak를 유지한다. Darwin이 cbreak→canonical 복원에서 원래 없던 PENDIN을 추가한 경우에만 입력 flush로 그 새 상태를 제거하며 원래 PENDIN=1에는 flush하지 않는다. 이 경우 대기 중 입력 바이트는 버려질 수 있다. 전체 typed termios의 앱-finally 복원과 나중 interactive shell/ZLE idle 상태는 별도 관측이며, 이전 실패 receipt를 통과로 재분류하지 않는다.

## 화면

한 행 overview는 전체 목표의 오류/확인 대기/기록상 통과와 `사용자 확인: 미관측`을 분리한다. task가 모두 통과해도 목표/사용자 승격은 없다. 조직 보기에는 명시 team ID와 lead/member, claimed와 수락 미확인을 보존한다. 흐름/통합의 조용한 팀 lane에는 제목을 앞세운 노드, 한국어 상태·분류, 실제 할당/계획 모델과 검증된 전문가 표기를 둔다. 실제 specialist 없음과 미확인은 구별한다. `tasks[].parent`는 accepting actor이므로 조직/작업의 부모로 쓰지 않는다.

* org: 회사/head와 팀 lead/member. flow/combined: 원래 Task 순서를 유지하는 카드지도, `predecessor → consumer`의 정확한 선행 연결. 카드 아래 경계의 팀 표기와 선택 작업의 팀을 구별하고 t로 팀 범위를 선택한다. 같은 팀이라고 간선을 만들지 않는다. 위치는 실행 순서/병렬 실행이 아니며 등록 profile을 실시간 인원으로 승격하지 않는다.
* 넓은 지도는 실제 cell 폭·제목/메타데이터 wrap 높이·4셀 가로 gutter·2행 세로 간격을 재서 행을 채운다. 제목 첫 구간은 위 경계에 있고 나머지는 카드 안에서 줄바꿈한다. 분류/상태, 정확한 할당 또는 계획 모델, 근거 있는 전문가를 각 카드에서 읽는다. 네 카드 상한이나 빈 제목 예약행은 없다. 긴 카드가 높이에 맞지 않으면 `~ s 원문`으로 부분 표시를 밝힌다. `j/k`와 `s`, 원문 `n/p`로 전체 제목/ID/모델/배정·출처에 접근한다. 상태만 바뀌면 원래 ID/선택/쪽 offset과 지도 기하가 유지된다. resize는 같은 선택을 새 물리 크기에 재배치한다.
* 실제 연결만 빈 gutter로 개별 경로를 그리며 경로/포트를 공유하지 않는다. 연결할 수 없는 정확한 간선은 `미표시 N연결`로 따로 세고, 모든 작업의 `l`에서 양 끝 이름과 **전체 source ID**를 줄바꿈·쪽으로 읽고 Enter로 반대편에 간다. 카드 모두 보임은 전체 간선이 그려짐을 뜻하지 않는다. `연결 일부만 기록`은 입력 coverage이고 `미표시`는 이번 화면 기하이므로 다르다. fake bus, 전체 상호연결 또는 팀 DAG를 만들지 않는다. 개요/구간은 기록된 Kahn층 3개씩의 작업 묶음이며 시간·critical path·실행 관측이 아니다.
* 개요/구간은 같은 3-Kahn층 범위의 **작업묶음 요약카드**다. 대표 제목은 그 묶음 첫 작업의 원래 제목이며 실제 작업명을 바꾸지 않는다. `내부 N작업 생략`과 실제 내부 의존 수를 표시한다. 인접한 요약카드의 화살표에 원래 경계 간선 수를 집계하며, 개별 작업의 전체 상호연결·팀 DAG·실행 순서를 뜻하지 않는다. 건너뛰는 경계나 화면 밖 집계는 미표시 집계로 따로 세고, Enter로 해당 범위에 들어간 뒤 각 작업의 l에서 정확한 양 끝 ID를 읽는다. j/k는 모든 묶음에 도달하고 Enter/b는 같은 범위로 진입/복귀한다. 긴 대표 제목/낮은 화면에서는 제목·집계 수를 자르지 않는 n/p 텍스트 연속 페이지를 쓴다.
* 좁거나 높이7/8/9에서는 실제 필드 텍스트를 유한 페이지로 나누고 종료 q를 먼저 둔다. 출처 한 줄이 맞지 않는 폭에서는 `합성 시연/기록 주장`, `연결 일부/연결 불명`, `관측 없음`(ASCII: SYNTHETIC/RECORDED, PART LINKS/LINKS ?, NO LIVE)을 줄로 나누어 모두 보존한다. 그때 긴 목표/팀 안내 대신 화면·쪽과 실제 정보 본문을 두며 전체 목표·배정·출처는 s 원문에서 읽는다. 12×7 같은 첫 사용 가능 화면은 본문 한 행만 남아 연속 페이지가 더 많다. 조직도 원래 선언을 줄바꿈·쪽으로 읽으며 실시간 인원으로 승격하지 않는다. **height<7 또는 width<12는 종료 q를 먼저 보여 주는 확대 전용 단일 화면**이며 n/p 작업 접근을 광고하지 않는다. 1×1에는 q만 들어간다. 오른쪽과 마지막 한 cell/row를 비워 wrap/scroll을 피한다. 기존 `legacy`는 이전 @N/양 끝 주 페이지/ID 연속 페이지와 작은 graph slice의 검증 가능한 호환 경로로 유지한다.
* 색 모드는 실제 노드 state에 결합한 상태 구간만 의미색으로 표시한다(통과 녹색, 제출/선행 대기 황색, 단계/기록 오류 적색, 미확인 기본 전경). 제목 구간은 bold/기본 전경이고 필수 분류·모델·전문가 메타데이터는 faint 처리하지 않는다. 제목/모델에 포함된 «오류/대기» 문자열은 색상 근거가 아니다. ANSI를 제거한 색 프레임은 같은 무색 프레임과 문자 단위로 일치하며 ASCII/NO_COLOR는 SGR이 없다. 호스트 테마 대비·폰트 픽셀은 별도 실제 창 심사 사항이다.
* 화면 상태: `작업 검토 통과`(ACC: execution/independent technical/parent integration 세 stage earned_success), `제출·검토 대기`(SUB), `선행 작업 대기`(WAIT), `단계 검증 오류`(FAIL), `작업 기록 오류`(ERR), `상태 미확인`(?). 기존 checker 우선순위 FAIL→ERR→ACC→SUB→?를 보존한다. needs 미충족으로 WAIT를 덧씌우는 것은 원래 ?일 때뿐이다. recorded live를 RUN/미시작으로 승격하지 않는다. `연결 일부만 기록`과 `연결 정보 미확인`은 다르며 명시 []도 독립/ready/미시작의 증거가 아니다. goal acceptance는 task와 별도이며 실제 eligibility/scheduler/overlap은 unknown.
* source claims의 team/actor가 있어도 실제 staffed 조직 인증이 아니다. `?`는 명시 수락 증거 없음, `*`는 수락 **주장**이 있다는 표시이고 독립적인 host authentication이 아니다. 여섯 role registry가 여섯 실팀이라는 추론 금지.
* C0/C1/ESC/bidi-format 문자는 안전 대체한다. CJK display cells를 계산하지만 emoji ZWJ/ambiguous-width와 사용자 font/theme 대비는 터미널 차이가 남는다.


### 표시 사전과 할당 근거

분류의 고정 번역은 general=일반, language=언어, structured_data=구조화 데이터,
reasoning=추론, code=코드, research=조사, visual=시각, design=설계,
media_generation=미디어 생성, tool_use=도구 활용이다. 분류에서 팀/전문가를 추론하지 않는다.
ASCII에서는 같은 분류를 general/language/data/reasoning/code/research/visual/design/media gen/tool use로 쓴다.

모델은 `할당:`과 `계획:`을 구별한다. 둘 모두 serving 관측을 뜻하지 않는다.
명시 opaque 예시 `m1`, `fixture-model`은 `모델명 미확인 · 할당/계획 ID:`로 남긴다.
임의 짧은 custom ID는 placeholder라고 추정하거나 실제 제품명에 매핑하지 않는다.

검증된 specialist.status=assigned 이후에만 아래 exact native ID를 한국어로 표시한다.
사전 근거는 실제 agents/founder.json, planning.json, development.json, design.json,
marketing.json, qa-release.json의 id/name/native_agent.name이다. profile 존재만으로 배정하지 않는다.

| 정확한 native ID | 표시 |
|---|---|
| agent-company-founder | 창업 전문가 |
| agent-company-planning | 기획 전문가 |
| agent-company-development | 개발 전문가 |
| agent-company-design | 디자인 전문가 |
| agent-company-marketing | 마케팅 전문가 |
| agent-company-qa-release | QA·출시 전문가 |

그 외 배정된 custom ID는 `전문가명 미확인: <source ID>`, known none은 `전문가 없음`,
unknown은 `전문가 미확인`이다. full source ID는 `--once --json`의 tasks[].specialist.id에 유지한다.
역할/classification/model에서 한국어 전문가 배정을 만들지 않는다. 합성 입력은 `합성 시연`을
항상 표시하고 실제 작업자/serving/사용자 확인으로 제시하지 않는다.

## 일반 record 직접 입력 / 선택 metadata

```python
status_tui_input.load_record_snapshot(record_path, metadata_path=None, *, context_path=None)
```

기존 [record contract](record-contract.md)의 version-1 record와 기존 `status_view.build_view`/checker를 그대로 사용한다. 입력은 실제 스키마의 기록된 주장이지 실행 권한·작성자 인증·실제 staffed Run의 증거가 아니다. 합성 record의 `synthetic` 표지도 보존한다.

* 각 snapshot의 `input_mode:record`, `record_observation:{path,sha256,identity}`와 `input_observations`가 실제 읽은 바이트·device/inode/mode/size/mtime_ns/ctime_ns를 결합한다. `binding.record_sha256`는 **그 read에서 관측한 현재 record digest**이지 승인받은 불변 pin이 아니다. 처음부터 끝까지 identity/bytes가 유지되는지 재검사하고, 교체/race/goal·task revision 불일치는 전체 candidate를 거부한다. 여러 파일의 분산 원자적 snapshot이나 ABA 불가능성을 보장하는 OS transaction은 아니다.
* record만 주면 조직·팀·담당 actor·specialist·classification·작업 제목·dependencies는 미상이다. title/class/model/specialist 미상은 제목/분류/모델/전문가 미확인으로, 소속은 미확인 lane으로 표시한다. record의 명시 `task.model.requested` 또는 exact current Task/Dispatch/scope/revision에 결합된 `routing_decision.selected.model`만 할당 모델로 표시할 수 있다. 둘이 모순되면 거부한다. observed serving/role/parent/model/registry에서 조직·전문가·DAG를 추론하지 않으며 임의 annotation을 metadata 증거로 취급하지 않는다.
* record의 `evidence.file/sha256`는 여전히 **선언된 불변 pin**이다. 명시된 host-catalog manifest의 receipt/raw response와 checked receipt의 refreshed catalog 참조도 전이적으로 추적한다. 선언된 goal-evidence sidecar는 현재 읽은 bytes로 추적한다. 임의 JSON의 path나 private session/home을 탐색하지 않는다. 기존 checker의 현재 policy/config/semantic-settings 검사는 그대로이며, 이 환경 전체가 `input_observations`로 원자적으로 고정됐다고 주장하지 않는다.
* 선택 metadata는 아래의 **원래 `company-status-tui-input/v1` manifest**다. record source가 CLI로 선택한 **동일한 절대 경로**여야 하며, 기존 선언 SHA/scope/revision/source pins를 변경 없이 대조한다. 같은 bytes를 다른 경로에 복사한 record도 잘못된 attachment로 거부한다. 정상 metadata는 explicit 조직/제목/분류/전문가/계획을 보완한다. omitted task metadata의 제목은 미상이며 명시 record 모델만 사용할 수 있다.
* metadata가 stale이면 최신 record와 예전 조직/계획을 합치거나 source SHA를 자동 재작성하지 않는다. 상주 중 전체 candidate를 거부하고 ERROR+last-good를 표시한다. 이 고정 metadata를 계속 쓰려면 담당자가 새 버전을 명시적으로 공급해야 한다. **기본 `--record` 단독 모드는 metadata가 필요 없으므로 record 변경만으로 계속 갱신된다.**

```sh
python3.13 -B /path/to/company-orchestration/scripts/status_tui.py --record /private/run/record.json --metadata /private/run/view.json --once --json
```

일반 reader는 in-memory attachment/projection만 수행한다. runtime manifest/log/record/cache 쓰기, 스케줄러/병렬 상태 원장, Orca/provider 호출, 자동 staffing 수집이 없다. 잘못된 입력은 기존 checker 오류를 성공으로 바꾸지 않는다.

## Enriched 상주 입력: 명시 planning context capture

제목·분류·팀·실제 specialist·명시 needs가 이미 있는 유효한 계획 metadata를 사용한다. 없는 필드를 자동 생성하는 기능이나 새 staffed Run 인증은 아니다. 기존 `--metadata`를 그대로 사용하면 이전 절의 immutable/stale 정책이 적용된다. **같은 goal/revision/Task/current Dispatch 할당 안에서 실행·수락 상태만 계속 갱신**하려면 최초 한 번 다음처럼 캡처한다.

```sh
# caller가 미리 소유한 기존 private 디렉터리(mode 0700)에 NEW 파일을 지정한다.
python3.13 -B /path/to/company-orchestration/scripts/status_tui.py --record /private/run/record.json --metadata /private/run/view.json --capture-context /private/view/context.json
python3.13 -B /path/to/company-orchestration/scripts/status_tui.py --record /private/run/record.json --context /private/view/context.json
python3.13 -B /path/to/company-orchestration/scripts/status_tui.py --record /private/run/record.json --context /private/view/context.json --once --json
```

* `--capture-context`는 `--record`와 유효한 `--metadata`를 모두 요구하며 `--context/--once/--json`과 함께 쓸 수 없다. JSON capture receipt를 출력하고 종료한다. 디렉터리를 만들지 않는다. 기존 출력 경로·symlink 구성요소·group/other 접근이 있는 출력 parent·다른 uid parent·비정규 파일·관측된 race를 거부한다. mode0600의 exclusive new file만 쓰고 bytes/identity를 읽어 확인한다. 실패한/raced 출력은 성공으로 선언하지 않으며 operator는 원인을 확인하고 새 경로를 골라야 한다. 원래 record·metadata·source·승인·설치 경로에는 쓰지 않는다.
* 불변 `company-status-tui-context/v1`은 exact goal_id/scope/revision, 선택 record 절대 경로와 최초 digest, 원래 metadata 경로/digest, Task 순서·ID/current Dispatch/execution.actor/requested model/full routing assignment, static source/transitive pins를 캡처한다. actor/model이 record의 알려진 할당과 충돌하면 **capture부터 거부**한다. unknown도 고정된 unknown이며 나중에 새 할당으로 자동 바인딩하지 않는다. 원래 metadata 파일은 유지해야 한다.
* 매 refresh 원래 metadata와 비record 조직/계획/registry/assignment/audit 출처를 그대로 pin 검증한다. 원래 record를 task-ID 근거로 쓴 `/tasks/N`만 최소 `{id, assigned_model?}` planning fact로 캡처한다. 기록된 execution/result/technical/parent acceptance를 context에 복제하지 않는다. record를 조직·specialist·needs의 지속 근거로 겸용하면 capture가 거부되므로 그 근거는 별도 immutable 출처로 제공한다. arbitrary annotation/label/role registry로 빈 필드를 채우지 않는다.
* `--context` reader는 **무쓰기**다. 위 할당과 Task 집합/순서가 같으면 fresh record의 실제 SHA와 기존 checker를 사용한다. ACCEPTED→SUBMITTED→ACCEPTED에서 context/metadata/hash를 caller가 편집할 필요가 없다. goal/scope/revision, Task/Dispatch/actor/model/routing assignment 또는 원래 planning source가 바뀌면 전체 candidate 거부한다. 새 계획에는 담당자가 새 metadata와 NEW context를 명시 준비해야 하며 silent repin/partial stale-org merge/자동 재capture는 없다.
* stage·checker·goal acceptance는 **현재 record**에서만 계산한다. context의 조직은 planning claim일 뿐이고 capture 당시 조직 acceptance도 현재 acceptance로 승격하지 않아 `acceptance:unknown`으로 표시한다. 실제 consent/staffing/liveness/overlap/launch authority는 인증하지 않는다. `context_provenance`에 capture 근거를 보존한다. source hash와 caller 소유 파일은 저자 인증·서명이 아니며 분산 파일들의 원자적 transaction/ABA 방지를 보장하지 않는다.

공개 producer `status_tui_context.capture_context(record_path, metadata_path, output_path)`와 pure consumer `load_context_snapshot(record_path, context_path)`를 사용한다. 이 작은 계획 캡슐은 mutable execution ledger나 scheduler가 아니다.

## 기존 출처 결합 입력 v1 (`--manifest` / 선택 `--metadata`)

공개 pure seams ([넓은 카드 배치](../scripts/status_tui_wide.py), [범위·선택 탐색](../scripts/status_tui_navigation.py), 넓은 지도 회귀 테스트):

```python
status_tui_data.load_snapshot(manifest_path)  # -> company-status-tui/v1 dict
status_tui.render_frame(snapshot, width, height, mode='combined', page=0, color=False, *, ascii=False, layout='wide', state=None, palette='light')
status_tui.page_count(snapshot, width, height, mode='combined', *, layout='wide', state=None, ascii=False)
```

입력 `schema:company-status-tui-input/v1`, integer `version:1`. 정확한 keys는 `schema/version/binding/sources/record/organization/tasks/dependencies`. unknown/duplicate key, NaN, bool version, 잘못된 type/ID/cycle/모호 join은 거부한다. 최대 source256, 배열2000, source16MiB. 경로 각 구성요소의 symlink, 비정규 파일, source byte/hash/identity 변경을 거부하며 snapshot 후 전 원문을 다시 검사한다.

* `binding:{goal_id,scope,revision,record_sha256}`는 pinned record.goal과 정확히 같아야 한다. source `{id,path,sha256,kind}`의 유일 ID,64hex SHA256, 경로는 manifest 기준. kind=`record|org_manifest|org_handoff|claims|plan|registry|assignment|observation`. record는 source ID다.
* 원래 record의 explicit evidence.file/sha256, org manifest/handoff의 explicit sources/path/sha256도 읽고 최종 `input_pins`에 포함한다. 이 명시적 전이 참조 외의 세션/디렉터리를 탐색하지 않는다. 기존 record checker가 현재 policy/config를 읽는 동작은 그대로 유지한다.
* organization=null은 조직 미기록. 있을 때 `{head,teams}`. head/lead=`{actor,evidence}` 또는 null, team=`{id,label,lead,members,evidence}`, member=`{actor,evidence}`. evidence=`[{source,pointer}]`, RFC6901 pointer 존재/actor 및 정확한 관계·팀과 scope/revision를 확인한다. claims 원문은 예컨대 `{scope,revision,head:"head-id",teams:[{id,label,lead:"lead-id",members:["member-id"]}]}`. scalar 포인터라도 `head`(같은 object의 teams 존재), `teams[i].lead`, `teams[i].members[j]`의 실제 조상 관계와 팀 ID를 확인한다. structured actor object 및 그 `/actor` child도 조상 관계를 유지한다. 별도 structured evidence는 `{actor,relation|role:'head|lead|member',team_id}`를 명시해야 한다(head는 팀 없음). actor만 같은데 관계/팀이 부족하면 unknown이며 누락 team_id를 요청 팀으로 채우지 않는다. 다른 팀·역할·actor나 조상/explicit field 충돌은 전체 거부한다. 유효 근거 하나가 다른 모순 근거를 덮지 않는다. 이 형태 자체는 수락/consent 인증이 아니다.
* org_manifest/org_handoff는 실제 `org_audit.audit/import_handoff`를 호출한다. 원래 field_status, observation/declaration와 unknown/issues를 `org_audits`에 보존한다. inconsistent는 입력 거부, incomplete는 경고. event.depends_on을 task needs로 복사하지 않는다.
* tasks attachment=`{id,title,classification,team_id,actor,assigned_model,specialist,evidence}`. record.tasks ID와1:1 join, 중복/orphan/current revision mismatch 거부. 누락 attachment의 실제 record task는 지우지 않고 미배정/unknown으로 표시한다. team_id/actor/model/classification nullable. team ID는 명시 조직에 있어야 한다. classification은 기존 worker-profile family vocabulary. 할당 모델은 current-bound routing_decision/task.model.requested와 모순되면 거부한다. 원래 할당이 없는 별도 계획 모델은 같은 task의 source evidence에 assigned_model이 있어야 하며 `계획:`으로 표시한다. serving/observed와 다르다.
* specialist=`{status:'assigned|none|unknown',id,evidence}`. assigned는 pinned **agents/*.json profile shape**의 `native_agent.name`에 정확히 있는 native ID와 explicit assignment(`task,dispatch,actor,specialist`)가 current Task/Dispatch에 결합돼야 한다. role family/skill/model으로 채우지 않는다. none도 동일 assignment의 `specialist:null` 근거 필요. unknown은 id:null. registry는 ID allowlist이며 roster가 아니다.
* dependencies=`[{task,needs,evidence}]`. 명시 pinned plan 원문의 동일 `{task,needs}`와 같아야 한다. cycle/self/orphan/duplicate edge/consumer 거부. 전부 미제공은 coverage unknown. 각 task의 명시 row가 있어야 그 row의 기록된 선행조건 충족 여부만 계산하며 실제 실행 자격/생존은 추정하지 않는다.

projection은 `binding/organization/tasks/dependencies/warnings/sources/generated_at/captured_at/live_host_state:'unknown'`, 기존 view의 `goal/check/summary/overall_goal_acceptance/historical_integrity/current_readiness`와 stage별 원문 검사를 보존한다. invalid record를 UI 성공으로 덮지 않는다. source pin은 bytes 대조이지 작성자/승인 인증이 아니다.

## 검증·패키지 경계

```sh
# company-orchestration/scripts 안에서
python3.13 -B -m unittest test_status_tui_data test_status_tui -v
python3.13 -B -m unittest test_status_tui_input -v
python3.13 -B -m unittest test_status_tui_context -v
python3.13 -B -m unittest test_status_tui_wide -v
```

synthetic source-bound multi-team DAG와 actual CLI owned PTY tests가 분리돼 있다. renderer80×12/120×20/48×12/short,80×24/120×40, paging/control-injection/empty; CLI JSON/errors; 실제 PTY update/idle/no-redraw/modes/page/resize/NO_COLOR/ASCII/error-last-good/recovery/q/SIGINT/SIGTERM와 termios semantic/exact/프로세스 회수를 검사한다. optional `COMPANY_TUI_TEST_EVIDENCE=/owned/path`는 테스트 harness의 원본 PTY bytes/restore receipt 저장용이며 제품 실행 경로는 audit/log 파일을 쓰지 않는다.

새 adapter suite는 기존 Company schema corpus의 record를 실제 `--record` CLI와 소유 PTY에 공급한다. manifest 없이 record-only 상태 변경, malformed/revision/evidence 오류와 last-good 복구, byte-identical 교체 identity race, optional metadata의 활용/불변 pin, 미상 필드와 무쓰기를 검사한다. 실제 staffed Run capture나 실제 host pane 설치를 뜻하지 않는다.

context suite는 explicit capture/new-file guard와 원래 source/assignment 충돌 거부, 무쓰기 refresh, checker 오류 보존, 실제 CLI 및80×12 PTY에서 작업 검토 통과→제출·검토 대기→통과의 enriched fields/실제 경계 간선 유지와 mismatch ERROR+last-good/cleanup을 검사한다. 기존 표현 token만 한국어/지도 기하로 교체하며 부정 시험은 유지한다. 가산 graph suite는 chain/fork/fan-in/diamond/교차 팀/분리 작업, 모든 작업·간선·양 끝 쪽, 상태 안정성, 모델/전문가 unknown/none,10개 분류, 긴 공통-prefix ID, CJK/주입, NO_COLOR/영어 ASCII와 신규 helper managed bytecode poison을 검사한다. 최종 source/official stage policy·closure·public maintenance 증거는 정확한 후보별로 별도 보존한다.

이 새 skills 하위 파일은 기존 installer의 recursive COPY_ENTRIES에 포함된다. source tests는 installed host lower-pane/upper input 보존이나 실제 Company staffing의 증거가 아니다. 실제 staging/closure/managed activation/host pane/fleet는 각각 담당자가 확인해야 한다.
