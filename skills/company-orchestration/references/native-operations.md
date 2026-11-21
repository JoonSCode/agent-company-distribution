# Company-native operations

`native_operations.py`는 Company 자체 stdlib 구현이다. Claude binary·계정·API·plugin은 필요 없다. 기존 Run retention, Codex receipt parser, approved router와 checked launcher를 재사용한다. 앱 전체 캐시 청소/계정 청구/현재 대화의 추론 모드 전환을 흉내 내지 않는다.

## 진입점과 반환

패키지의 `scripts` 디렉터리에서 기존 Python 3.13+로 실행한다. 모든 명령은 stdout에 단일 JSON, exit 0=보고/prepared/completed, 1=현재 상태/권한 guard 차단, 2=형식/출처 충돌이다. 도움말만 일반 argparse 텍스트다. report/plan/closeout은 read-only다. enroll/classify는 명시한 새 Run metadata, prepare는 명시한 새 private bundle을 쓴다. glob·자동 session/home discovery·모델 호출은 없다. `settle-launch`만 명시한 실행 파일에 exact Dispatch 종료 readback을 요청하며 새 worker를 시작하지 않는다.

```sh
python3 -B native_operations.py storage report --request /private/storage-request.json
python3 -B native_operations.py storage plan --request /private/storage-request.json
python3 -B native_operations.py usage report --request /private/usage-request.json
python3 -B native_operations.py reasoning prepare --request /private/reasoning-request.json --output /private/new-exclusive-bundle
python3 -B native_operations.py reasoning check --bundle /private/new-exclusive-bundle
```

요청 JSON은 아래 명시 필드만 받는다. 중복 키·NaN·path traversal·symlink·hardlink 입력·깨진 SHA256을 거부한다. 상대 파일 참조는 **요청 파일 기준**이다. 해시는 lowercase 64 hex의 실제 원문 SHA256이어야 하며 placeholder는 입력으로 유효하지 않다. Pin은 출처 바이트 일치이지 출처 인증/사용자 승인이 아니다.

## Storage: enrollment, classification, closeout

새 supported 작업은 [native storage lifecycle](storage-lifecycle.md)의 enroll → reserve → writer → checked launch의 별도 exact exit/consumer settlement → freeze → accepted plan/apply → read-only closeout 순서다. `enroll`/`classify`는 명시한 새 Run metadata를 쓴다. `maintenance-plan`은 별도 current authority preview이며 `maintenance-apply`는 독립 exact review와 실제 owner approval 없이는 동작하지 않는다. 기존 v1 report/plan/apply 형식은 유지한다. Closeout은 실제 receipt를 읽어 not_enrolled/skipped/blocked/removed/unknown과 null-vs-zero, trigger, pending owner를 구분한다. JSON의 `final_summary`는 실제 관측/이전 receipt를 명시한 일반 최종 응답용 문장이다. 새 실행이나 APFS 절감으로 해석하지 않는다. `status_view.py render RECORD --storage-closeout-request EXACT`는 같은 canonical record/goal/owner의 read-only 결과를 HTML/JSON에 표시한다. 요청 미제공은 unknown이며 0으로 만들지 않는다. Codex Stop stdout `{}`는 그대로 프로토콜이다.

`storage maintenance-closeout --request EXACT`는 별도 `company-native-storage-maintenance-closeout-request/v1` 요청의 정확한 `schema`, `plan`, `authorization`, `review`만 받는다(세 문서는 `{path,sha256}`). 원래 plan/request/auth/review와 external sink, root identity, preserved/historical metadata, 실제 부재/removed prefix를 다시 읽는다. receipt가 없으면 unknown, partial/pending/reappearance/stale/newer rejection은 blocked다. 이 명령은 apply/retry/init/register를 실행하지 않으며 actor 문자열을 실제 독립 승인으로 인증하지 않는다.

## Storage: explicit Run만

요청 `schema: company-native-storage-request/v1`:

* `roots`: `{path,kind:"company-run",run_id,owner}` 배열. `sejong_home/runs/` 하위의 정확한 Company-owned Run 경로만. 전체 홈/디스크/다른 앱을 스캔하지 않는다.
* `sejong_home`: 명시 Run store 경로.
* `record`: Run 내부의 상대 accepted record 경로.
* `expect_manifest_sha256`: 현재 `retention-manifest.json`의 SHA256.

`report`는 각 root의 파일 목록, files/bytes, `declared_disposable|preserved|protected|unknown` breakdown, 현재 readiness와 blockers를 반환한다. unregistered 파일은 unknown, reserved metadata/record/evidence는 protected다. 불명/unreadable bytes는 null이지 0이 아니다. linked 디렉터리를 따라가지 않는다. 읽기 전용 preflight는 lock·receipt·metadata를 쓰지 않는다. `lsof`로 현재 activity를 확인하되 future quiescence를 보증하지 않는다. 필요한 probe가 없으면 차단한다.

`plan`은 **한 개 exact Run**만 지원한다. roots 배열을 받는 report와 달리 여러 root를 한꺼번에 적용하지 않는다. `company-native-storage-plan/v1`은 original request pin, root device/inode, record path/hash/identity, manifest CAS, disposable/preserve identity/hash, inventory pin, expected bytes, blockers와 `apply_authorized:false`를 담는다. stdout을 새 파일로 저장하려면 Run 밖의 별도 owned 경로를 쓴다. 저장/입력 변경도 이후 plan을 stale하게 만들 수 있다.

소유자가 별도로 실제 삭제를 승인한 경우에만 다음 **명시 apply**를 사용할 수 있다. 이 문서나 plan 생성은 삭제 승인이 아니다.

```sh
python3 -B native_operations.py storage apply --plan /private/owned-plan.json --expect-plan-sha256 ACTUAL_PLAN_FILE_SHA256
```

apply는 plan 파일의 정확한 hash와 original request/현재 모든 guard를 다시 확인한 뒤 기존 `run_completion.main(["complete", ...])`를 한 번 호출한다. 별도 unlink/rmtree 구현은 없다. 원래 lock/CAS/quarantine/receipt guard를 유지하고 성공 receipt·제거 파일 부재·preserved byte/identity를 읽어 검증한다. 현재/미수락/settlement 미완료 Run, source/git worktree(깨끗한 tracked도 보수적으로 보호), uncommitted/untracked source, shared/hardlink, symlink, open/pinned, owner mismatch, stale manifest/record/target/root, evidence 삭제를 차단한다. 기존 completion attempt receipt가 있으면 native 자동 retry 대신 소유자 recovery가 필요하다. native 테스트의 apply는 disposable synthetic fixtures만 사용한다. 사용자 데이터 cleanup은 테스트하거나 승인하지 않았다.

비동등/손실: 전체 Desktop/VM/cache 및 inactive archive 관리 없음. Run 밖 미지원 bytes=null. 필요한 확장은 명시 owned-root registry와 resource별 adapter/retention authority다. Date/파일명으로 disposable을 추측하지 않는다.

## Usage: bound response union

요청 `schema: company-native-usage-request/v1`, `required_scopes:[string]`, `sources:[...]`.
각 source의 정확한 필드:

```text
id, provider, trace, sha256, turn_id, scope,
run_id, task_id, dispatch_id, actor, model,
binding: {path, sha256, pointer} | null
```

`run_id/task_id/dispatch_id/actor/model/turn_id`는 null을 허용한다. `binding.pointer`는 RFC6901 JSON pointer다. 선택된 source object는 `provider/session_id/turn_id/run_id/task_id/dispatch_id/actor/model`을 명시하고 실제 parser provenance/요청과 정확히 같아야 한다. 서로 충돌하는 값은 exit2다. source binding이 없으면 claimed, 값이 없으면 unknown이며 caller 문자열을 observed 실행 사실로 올리지 않는다. 합성 출처의 `synthetic:true`는 결과에 보존한다.

현재 adapter는 `provider:"codex"`의 명시 JSONL `token_usage_record`만 지원한다. 기존 `provider_usage.read_usage`의 provenance.responses를 `(provider,response_id)`로 합집합한다. 반복 export는 1회만, 같은 response의 usage/session/turn/cumulative 충돌은 오류다. cached input/reasoning output은 subset이므로 추가 합산하지 않는다. 하나의 response가 여러 Task/Run/actor/model에 걸치면 해당 grouping의 `shared/unallocated`로 한 번만 센다. Task grouping ID는 `[run_id,task_id,dispatch_id]`의 JSON 문자열이어서 서로 다른 Run의 같은 local task ID를 합치지 않는다. capture grouping도 반복 export에 토큰을 이중 배분하지 않는다.

결과 `company-native-usage/v1`:

* `coverage`, `required_scopes`, `missing_required_scopes`, 각 scope의 bound/claimed/unknown 상태.
* `observed_raw_total`: 실제 고유 response raw token의 알려진 부분 합; 아무 receipt도 없으면 null.
* `total_raw_tokens`: required scope가 명시되고 전부 complete/bound이며 unsupported/partial source가 없을 때만 숫자. 아니면 null. unknown attribution이 있는 grouping의 total도 null.
* `breakdown.run/task/actor/model/capture`, 각각 coverage/attribution/observed subtotal/complete total. 정산되지 않은 공유 response는 별도 unallocated bucket.
* deduped/duplicate count, unsupported source count, unknown attribution count와 근거 pins.

이 범위는 supplied capture denominator뿐이다. 전체 계정·24h/7d·fleet total, 달러/billing/free/savings, 자동 fix, skill attribution을 만들지 않는다. 미지원 provider는 unknown으로 남긴다. 다음 최소 확장은 해당 provider raw receipt→동일 response identity/coverage adapter다.

## Deep reasoning: 다음 checked launch만

새 prepare 요청 `schema: company-native-reasoning-request/v2` (v1 문서는 엄격한 기존 필드로만 읽으며 fresh prepare/launch 권한이 아님):

```text
depth: standard | deep | ultrathink
effort: explicit native-supported string
record: {path,sha256}
decision: {path,sha256}
spec_file: {path,sha256}
worktree: exact existing id:...::/... selector
enrollment: {path,sha256}  # actual existing storage enrollment
output_files: [original-record.json, original-decision.json, spec.txt, record.json, decision.json, patch.json, routing-check.json, missing-fields.json, manifest.json, native-reasoning.json]
```

`ultrathink`는 `deep`의 UX alias일 뿐이다. deep+기존 승인 low도 유효하며 xhigh로 자동 승격하지 않는다. 지원 enum은 Company가 발명하지 않고 승인된 router/catalog가 검사한다. request effort가 이미 승인된 selected effort와 다르면 blocked다. provider/model/service/paid-opt-in/config/catalog/spec/scope/revision/현재 policy pins는 기존 router 검사를 유지한다. 다른 provider를 요청하면 그 선택을 그대로 출력하면서 `checked_launch_bridge_unavailable`로 차단한다. Codex/paid fallback이나 global defaults 수정은 없다.

`routing_prepare.prepare`와 `check_bundle`가 실제 private bundle을 만든다. native sidecar는 original depth request pin과 requested/approved를 보존한다. `reasoning check`는 원래 요청·bundle·원문·현재 configuration/source/semantic bindings를 다시 확인한다. source policy hash drift는 차단이며 자동 sync/예외 처리하지 않는다. 준비 실패 시 partial bundle을 지우거나 자동 재준비하지 않는다.

성공 응답의 `next_checked_launch`는 checked `routing_launch.py`가 받는 `record/decision/spec_file/worktree`와 enrollment/prepared-bundle/run/parent flags를 반환한다. `record`는 편입된 Run의 canonical live record이고 bundle/record.json은 보존된 검토 snapshot이다. 두 원문을 현재 byte pin으로 cross-bind하며 canonical record 변경은 이전 bundle을 stale로 만든다. `routing_prepare.py prepare` 자체도 `--enrollment-request EXACT --expect-enrollment-sha256 SHA256`가 필수이고 fixed bundle/sidecar 파일은 생성 전 reserve한다. measurement lifecycle/canary CLI도 같은 flags를 전달하며 measurement-v2 consumer를 편입 때부터 명시한다. prepare/event/source-prefix/final/settlement writer는 각 다음 exact path를 생성 전에 preserve로 reserve한다. `spec_file`을 launcher flag로 전달하지 말고 그 **정확한 UTF-8 내용**을 `--spec`으로 넘겨야 한다. 호출자는 실제 승인된 `--from`, 사용하지 않은 `--receipt`와 `--result`를 명시해야 한다. existing/unknown result는 reconcile 전 재시도 금지다. launcher/ledger의 기존 stable lock은 삭제·이름 예외로 해제하지 않는다. 해당 activity marker 또는 미완료 creation reservation이 남으면 freeze/acceptance는 BLOCKED이며 migration 테스트 통과만으로 결합 lifecycle 완료를 주장하지 않는다.

resource manifest/effort cap/지출 ceiling은 이 frozen depth request에 제공되지 않으므로 **prepared가 cap 검증 완료/권한 증명이 아니다**. 해당 scope가 요구하면 unchanged launcher에 `--require-resource-manifest --resource-manifest ... --declared-host ... --declared-tool ... --declared-billing ... --declared-spend ...`를 정확히 제공한다. 원래 gate는 host subprocess 이전에 cap/budget mismatch를 차단한다. trusted capacity reservation/live quota는 unknown/미지원이다. 테스트는 실제 native bundle→unchanged checked launcher→counted fake-host positive, cap/spend/unknown-result negative를 검증한다. 실제 호스트/모델은 호출하지 않는다.

항상 `requested`/`approved`와 `effective:{model:null,effort:null,status:"not_launched"}`를 분리한다. 이 명령은 **다음 launch의 입력을 준비할 뿐 현재 turn이나 다음 turn의 실제 serving model/effort를 관측하지 않는다**. actual launch receipt 이전에 effective를 채우지 않는다. 최소 후속은 provider별 checked-launch/effective-readback adapter와 별도 resource declaration의 request binding이다.

## 검증

```sh
python3 -B -m unittest test_native_operations -v
```

테스트는 owned scratch와 합성 source-bound receipt/semantic DB/catalog만 쓴다. 설치/실제 사용자 cleanup/계정 usage/paid 모델/Orca host 실행 증거와 다르다. 명시 `NATIVE_OPS_RECEIPTS` artifact path가 있으면 exact CLI argv/stdout/stderr/exit 및 counted fake-launch 결과를 append한다. staged 테스트는 staged module `__file__` origin까지 검사한다. 마지막 policy digest closure와 source/staged 정합성은 정식 통합 단계가 소유한다.
