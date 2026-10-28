#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Freeze a bounded study and regrade saved outcomes; never launch or approve work.

Hash, denominator, duplicate-Dispatch and all-success arithmetic are adapted from
the accepted company-harness-audit-20261026/evaluation/score.py artifact. This
supported path adds task oracles and launch/brief/artifact bindings, not a scheduler.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from math import comb
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

# Select Python's normal cache prefix before importing Company modules.
# Restrict this to the CLI process; callers importing a module are unchanged.
if __name__ == "__main__":
    import os as _os
    import sys as _sys
    _sys.pycache_prefix = _os.path.join(_os.path.abspath(_os.path.expanduser("~")), ".cache", "agent-company", "python")

VERSION = "company-outcome-eval/v1"
LIMIT = 2_000_000
STATUSES = {"success", "failure", "environment_failure", "aborted", "unknown"}


class Invalid(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Invalid(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode()


def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2,
                      allow_nan=False) + "\n"


def decode(data):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON key: " + key)
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(Invalid("nonfinite JSON")))


def shape(value, keys, label):
    require(isinstance(value, dict) and set(value) == set(keys), "invalid fields: " + label)


def text(value, label):
    require(isinstance(value, str) and bool(value.strip()), "nonempty string required: " + label)


def identifier(value):
    require(isinstance(value, str) and re.fullmatch(r"[a-zA-Z0-9_-]+", value), "invalid id")


def local_name(name):
    require(isinstance(name, str) and name and not Path(name).is_absolute() and
            all(p not in ("", ".", "..") for p in name.split("/")) and "\\" not in name,
            "relative local path required")
    return name


def read_local(root, name):
    path = root
    for part in Path(local_name(name)).parts:
        path = path / part
        require(not path.is_symlink(), "symlink refused: " + name)
    require(path.is_file(), "missing evidence: " + name)
    require(path.stat().st_size <= LIMIT, "oversized evidence: " + name)
    return path.read_bytes()


def bound(root, reference):
    shape(reference, {"path", "sha256"}, "file reference")
    require(isinstance(reference["sha256"], str) and
            re.fullmatch(r"[0-9a-f]{64}", reference["sha256"]), "sha256 required")
    data = read_local(root, reference["path"])
    require(sha(data) == reference["sha256"], "evidence hash mismatch: " + reference["path"])
    return data


def put(root, name, data):
    path = root / local_name(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)
    return {"path": name, "sha256": sha(data)}


def file_tree(root):
    require(root.is_dir() and not root.is_symlink(), "artifact directory required")
    paths = sorted(root.rglob("*"))
    require(len(paths) <= 100, "at most 100 artifact paths allowed")
    require(all(not p.is_symlink() for p in paths), "artifact symlink refused")
    return {p.relative_to(root).as_posix(): read_local(root, p.relative_to(root).as_posix())
            for p in paths if p.is_file()}


def task_specs(data):
    shape(data, {"format", "tasks"}, "task specifications")
    require(data["format"] == "company-outcome-tasks/v1" and
            isinstance(data["tasks"], list) and data["tasks"], "task specifications required")
    tasks = {}
    for task in data["tasks"]:
        shape(task, {"id", "version", "brief", "initial", "writable", "oracle"}, "task")
        identifier(task["id"])
        require(task["id"] not in tasks, "duplicate task id")
        text(task["version"], "task version")
        text(task["brief"], "task brief")
        require(isinstance(task["initial"], dict) and task["initial"], "initial files required")
        for name, content in task["initial"].items():
            local_name(name)
            require(isinstance(content, str), "initial contents must be text")
        require(isinstance(task["writable"], list) and task["writable"] and
                len(set(task["writable"])) == len(task["writable"]), "writable files required")
        for name in task["writable"]:
            local_name(name)
        oracle = task["oracle"]
        require(isinstance(oracle, dict), "oracle required")
        if oracle.get("kind") == "python_function":
            shape(oracle, {"kind", "path", "function", "cases"}, "python oracle")
            local_name(oracle["path"])
            identifier(oracle["function"])
            require(isinstance(oracle["cases"], list) and oracle["cases"], "oracle cases required")
            for case in oracle["cases"]:
                shape(case, {"args", "expected"}, "function case")
                require(isinstance(case["args"], list), "case arguments required")
        else:
            shape(oracle, {"kind", "path", "expected"}, "JSON oracle")
            require(oracle["kind"] == "json_equal", "unsupported oracle")
            local_name(oracle["path"])
        tasks[task["id"]] = task
    return tasks


def conditions(plan, arm):
    return {**plan["common"], "instruction": plan["arms"][arm]}


def trial_binding(plan, plan_hash, trial):
    return {"plan_sha256": plan_hash, "trial_id": trial["id"], "task_id": trial["task"],
            "arm": trial["arm"], "task_sha256": sha(canonical(plan["tasks"][trial["task"]])),
            "candidate_sha256": plan["arms"][trial["arm"]]["sha256"],
            "conditions_sha256": sha(canonical(conditions(plan, trial["arm"])))}


def load_plan(path, expected_hash):
    root = path.parent.resolve()
    data = read_local(root, path.name)
    require(sha(data) == expected_hash, "plan anchor mismatch")
    plan = decode(data)
    shape(plan, {"format", "study", "evidence_class", "source_commit", "grader_sha256",
                 "common", "arms", "tasks", "expected_trials", "pass_k"}, "plan")
    require(plan["format"] == VERSION and plan["study"] == "feasibility", "unsupported plan")
    require(plan["evidence_class"] in {"synthetic", "real"}, "invalid evidence class")
    text(plan["source_commit"], "source commit")
    require(plan["grader_sha256"] == sha(Path(__file__).read_bytes()), "grader hash mismatch")
    shape(plan["common"], {"route", "agent", "model", "effort", "context", "tools", "authority",
                           "receipt_mode", "session", "retry_policy", "timeout_seconds", "max_workers"}, "common conditions")
    for key in ("route", "agent", "model", "authority", "receipt_mode", "session", "retry_policy"):
        text(plan["common"][key], key)
    require(plan["common"]["route"] == "orca/" + plan["common"]["agent"], "route/agent mismatch")
    require(plan["common"]["effort"] is None or isinstance(plan["common"]["effort"], str) and
            plan["common"]["effort"].strip(), "effort must be observed string or unsupported null")
    require(plan["common"]["session"] == "fresh-per-trial", "fresh sessions required")
    require(plan["common"]["max_workers"] == 2, "pilot concurrency cap must be two")
    require(type(plan["common"]["timeout_seconds"]) is int and
            1 <= plan["common"]["timeout_seconds"] <= 3600, "invalid timeout")
    require(plan["common"]["tools"] == ["local-read", "isolated-file-write", "python"], "unsupported tools")
    bound(root, plan["common"]["context"])
    shape(plan["arms"], {"baseline", "candidate"}, "arms")
    for reference in plan["arms"].values():
        bound(root, reference)
    tasks = task_specs({"format": "company-outcome-tasks/v1", "tasks": list(plan["tasks"].values())})
    require(tasks == plan["tasks"], "task key/id mismatch")
    require(type(plan["pass_k"]) is int and 1 <= plan["pass_k"] <= 100, "invalid pass_k")
    require(isinstance(plan["expected_trials"], list) and plan["expected_trials"], "expected trials required")
    ids, cells = set(), Counter()
    for trial in plan["expected_trials"]:
        shape(trial, {"id", "task", "arm"}, "expected trial")
        identifier(trial["id"])
        require(trial["id"] not in ids, "duplicate expected trial")
        require(trial["task"] in tasks and trial["arm"] in plan["arms"], "unknown task/arm")
        ids.add(trial["id"])
        cells[trial["task"], trial["arm"]] += 1
    require(len(set(cells.values())) == 1 and
            len(cells) == len(tasks) * 2, "balanced planned cells required")
    return root, plan


def freeze(args):
    specifications = task_specs(decode(args.spec.read_bytes()))
    selected = args.tasks.split(",") if args.tasks else list(specifications)
    require(selected and len(set(selected)) == len(selected) and
            all(t in specifications for t in selected), "unknown/duplicate selected task")
    require(1 <= args.repeats <= 20, "repeats must be 1..20")
    # Read inputs before making the output directory. Existing bundles are never overwritten.
    inputs = {"baseline": args.baseline.read_bytes(), "candidate": args.candidate.read_bytes(),
              "context": args.context.read_bytes()}
    require(all(0 < len(data) <= LIMIT for data in inputs.values()), "nonempty bounded inputs required")
    args.out.mkdir(parents=True, exist_ok=False)
    refs = {key: put(args.out, "inputs/" + key + ".txt", value) for key, value in inputs.items()}
    plan = {"format": VERSION, "study": "feasibility", "evidence_class": args.evidence_class,
            "source_commit": args.source_commit, "grader_sha256": sha(Path(__file__).read_bytes()),
            "common": {"route": "orca/" + args.agent, "agent": args.agent, "model": args.model, "effort": args.effort,
                       "context": refs["context"], "tools": ["local-read", "isolated-file-write", "python"],
                       "authority": "Modify only trial writable files; no network, external actions, children, installation or source edits.",
                       "receipt_mode": "saved-raw-launch-and-worker_done; no receipt automation intervention",
                       "session": "fresh-per-trial", "retry_policy": "no automatic retry; preserve every planned attempt",
                       "timeout_seconds": 600, "max_workers": 2},
            "arms": {key: refs[key] for key in ("baseline", "candidate")},
            "tasks": {key: specifications[key] for key in selected}, "pass_k": 2,
            "expected_trials": [{"id": f"{task}-{arm}-{repeat}", "task": task, "arm": arm}
                                for repeat in range(1, args.repeats + 1)
                                for task in selected for arm in ("baseline", "candidate")]}
    ref = put(args.out, "plan.json", encode(plan).encode())
    load_plan(args.out / "plan.json", ref["sha256"])
    return {"format": VERSION, "plan": str(args.out / "plan.json"), "plan_sha256": ref["sha256"],
            "planned_attempts": len(plan["expected_trials"]), "launches_performed": 0}


def find_trial(plan, tid):
    matches = [t for t in plan["expected_trials"] if t["id"] == tid]
    require(len(matches) == 1, "unknown trial id")
    return matches[0]


def brief(root, plan, plan_hash, trial, workspace):
    task = plan["tasks"][trial["task"]]
    binding = trial_binding(plan, plan_hash, trial)
    return ("Bounded local feasibility trial. Follow the actual Orca worker preamble for lifecycle reporting.\n"
            "Fresh session; no helper workers, network, API, installation or edits outside the listed artifacts.\n"
            "The supplied instruction snapshot is the intervention; host/global policy remains authoritative.\n"
            "Do not read sibling trials, evaluator code or answer/oracle files.\n"
            "For every Python check use -B or PYTHONDONTWRITEBYTECODE=1 to avoid incidental cache artifacts.\n"
            + "Frozen binding: " + canonical(binding).decode() + "\n"
            + "Workspace: " + str(workspace.resolve()) + "\n"
            + "Writable files: " + ", ".join(task["writable"]) + "\n"
            + "Frozen requested route/agent/model/effort: " + canonical({k: plan["common"][k] for k in ("route", "agent", "model", "effort")}).decode() + "\n"
            + "Common context observations and limits:\n" + bound(root, plan["common"]["context"]).decode() + "\n"
            + "Supplied instructions:\n" + bound(root, plan["arms"][trial["arm"]]).decode() + "\n"
            + "When reporting worker_done, include actual edited paths with --files-modified; use absolute paths under this workspace.\n"
            + "Task:\n" + task["brief"] + "\n")


def prepare(args):
    root, plan = load_plan(args.plan, args.plan_sha256)
    trial = find_trial(plan, args.trial)
    args.workspace.mkdir(parents=True, exist_ok=False)
    for name, content in plan["tasks"][trial["task"]]["initial"].items():
        put(args.workspace, name, content.encode())
    text_bytes = brief(root, plan, args.plan_sha256, trial, args.workspace).encode()
    # Brief lives outside writable task artifacts; its bytes can be compared at collection.
    reference = put(root, f"briefs/{args.trial}.txt", text_bytes)
    return {"trial_id": args.trial, "binding": trial_binding(plan, args.plan_sha256, trial),
            "workspace": str(args.workspace.resolve()), "brief": reference,
            "brief_path": str(root / reference["path"])}


def envelope(data):
    document = decode(data)
    require(isinstance(document, dict) and document.get("ok") is True and
            isinstance(document.get("result"), dict), "successful Orca envelope required")
    return document["result"]


def execution(root, record, plan, seen, read_reference=None):
    read = read_reference or (lambda reference: bound(root, reference))
    launch = envelope(read(record["launch"]))
    ids = {key: launch.get(host) for key, host in
           (("run_id", "runId"), ("task_id", "taskId"), ("dispatch_id", "dispatchId"))}
    for key, value in ids.items():
        text(value, key)
    require(ids["dispatch_id"] not in seen, "duplicate actual Dispatch")
    seen.add(ids["dispatch_id"])
    launch_model = launch.get("launch", {})
    require(isinstance(launch_model, dict), "launch selection required")
    for selection in ("requested", "effective"):
        settings = launch_model.get(selection)
        require(isinstance(settings, dict) and all(key in settings for key in ("agent", "model", "effort")) and
                settings["agent"] == plan["common"]["agent"] and
                settings["model"] == plan["common"]["model"] and
                settings["effort"] == plan["common"]["effort"], "launch agent/model/effort mismatch")
    terminals = {e.get("id") for e in launch.get("effects", [])
                 if isinstance(e, dict) and e.get("kind") == "terminal" and e.get("role") == "agent"}
    require(len(terminals) == 1, "one launch executor required")
    actor = next(iter(terminals))
    text(actor, "launch executor")
    outcome, modified = None, None
    if record["worker_done"] is not None:
        done = envelope(read(record["worker_done"]))
        if "message" in done:
            messages = [done["message"]]
        else:
            require(isinstance(done.get("messages"), list), "Orca inbox messages required")
            messages = []
            for item in done["messages"]:
                if not isinstance(item, dict) or item.get("type") != "worker_done":
                    continue
                payload = item.get("payload")
                payload = decode(payload) if isinstance(payload, str) else payload
                require(isinstance(payload, dict), "worker_done payload required")
                if payload.get("taskId") == ids["task_id"] or payload.get("dispatchId") == ids["dispatch_id"]:
                    messages.append(item)
        require(len(messages) == 1, "exactly one matching worker_done required; duplicate/conflicting done refused")
        message = messages[0]
        require(isinstance(message, dict) and message.get("type") == "worker_done" and
                message.get("run_id") == ids["run_id"] and message.get("from_handle") == actor,
                "worker_done Run/executor mismatch")
        payload = message.get("payload")
        payload = decode(payload) if isinstance(payload, str) else payload
        require(isinstance(payload, dict) and payload.get("taskId") == ids["task_id"] and
                payload.get("dispatchId") == ids["dispatch_id"], "worker_done Task/Dispatch mismatch")
        outcome = payload.get("outcome")
        require(outcome in {"succeeded", "failed"}, "worker_done outcome required")
        if "filesModified" in payload:
            require(isinstance(payload["filesModified"], list), "worker_done modified files must be a list")
            modified = []
            for name in payload["filesModified"]:
                text(name, "modified artifact path")
                path = Path(name)
                if path.is_absolute():
                    # macOS /var and /private/var can name the same task directory.
                    path = path.resolve()
                    require(path.is_relative_to(Path(record["workspace"])), "worker_done artifact outside trial workspace")
                    name = path.relative_to(Path(record["workspace"])).as_posix()
                modified.append(local_name(name))
            require(len(set(modified)) == len(modified), "duplicate modified artifact path")
    return {**ids, "executor": actor, "outcome": outcome,
            "modified_artifacts": sorted(modified) if modified is not None else None,
            "launch_observation": launch.get("state"),
            "model_basis": "captured launch selection; not live provider identity"}


def collect(args):
    root, plan = load_plan(args.plan, args.plan_sha256)
    trial = find_trial(plan, args.trial)
    submitted = args.brief.read_bytes()
    require(submitted == brief(root, plan, args.plan_sha256, trial, args.workspace).encode(),
            "submitted brief/candidate/context mismatch")
    artifacts = file_tree(args.workspace)
    prefix = "trials/" + args.trial
    require(not (root / prefix).exists(), "trial already collected; preserve original attempt")
    raw = {"launch": args.launch.read_bytes(), "brief": submitted,
           "worker_done": args.done.read_bytes() if args.done else None,
           "trace": args.trace.read_bytes() if args.trace else None,
           "usage": args.usage.read_bytes() if args.usage else None}
    record = {"format": VERSION, "binding": trial_binding(plan, args.plan_sha256, trial),
              "reported_status": args.status, "workspace": str(args.workspace.resolve()),
              "artifacts": {name: {"path": prefix + "/artifacts/" + name, "sha256": sha(data)}
                            for name, data in artifacts.items()},
              **{name: None if data is None else {"path": prefix + "/" + name + ".txt", "sha256": sha(data)}
                 for name, data in raw.items()}}
    # Validate receipt bindings before writing a bundle. A launch observation gap is allowed.
    launch = envelope(raw["launch"])
    for key in ("runId", "taskId", "dispatchId"):
        text(launch.get(key), key)
    actual = execution(root, record, plan, set(),
                       lambda reference: next(data for data in raw.values()
                                              if data is not None and sha(data) == reference["sha256"]))
    for name, data in raw.items():
        if data is not None:
            put(root, record[name]["path"], data)
    for name, data in artifacts.items():
        put(root, record["artifacts"][name]["path"], data)
    ref = put(root, prefix + "/record.json", encode(record).encode())
    return {"trial_id": args.trial, "record": ref,
            "artifact_binding_sha256": sha(canonical(record["artifacts"])),
            "review_template": review_binding(record, actual, plan["evidence_class"])}


def review_binding(record, actual, evidence_class):
    return {**record["binding"], "dispatch_id": actual["dispatch_id"], "executor": actual["executor"],
            "artifact_binding_sha256": sha(canonical(record["artifacts"])),
            "assessor": None, "critical_failure": None,
            "basis": "synthetic_fixture" if evidence_class == "synthetic" else "independent",
            "note": "Independent reviewer must inspect originals, authority and actual artifact provenance."}


def oracle(task, artifacts, allow_task_code=False):
    protected = [name for name, value in task["initial"].items()
                 if name not in task["writable"] and artifacts.get(name) != value.encode()]
    unexpected = sorted(set(artifacts) - set(task["initial"]) - set(task["writable"]))
    critical = bool(protected or unexpected)
    check = {"critical_failure": critical, "protected_changed_or_missing": protected,
             "unexpected_files": unexpected, "passed": False, "exit_code": None}
    spec = task["oracle"]
    if spec["path"] not in artifacts:
        return {**check, "reason": "missing oracle artifact"}
    if spec["kind"] == "json_equal":
        try:
            actual = decode(artifacts[spec["path"]])
        except (ValueError, UnicodeError) as exc:
            return {**check, "reason": "invalid output JSON: " + str(exc)}
        return {**check, "passed": canonical(actual) == canonical(spec["expected"]) and not critical,
                "reason": "JSON final state comparison"}
    if not allow_task_code:
        return {**check, "reason": "task code execution not enabled"}
    # Explicit bounded local Python authority is part of the frozen plan. This is
    # code execution, not a sandbox; only use trusted isolated task artifacts.
    program = ("import json,sys\n"
               "def equal(actual, expected):\n"
               "    if type(actual) is not type(expected): return False\n"
               "    if type(expected) is dict:\n"
               "        return actual.keys() == expected.keys() and all(type(k) is str and equal(actual[k], expected[k]) for k in actual)\n"
               "    if type(expected) is list:\n"
               "        return len(actual) == len(expected) and all(equal(a, e) for a, e in zip(actual, expected))\n"
               "    return actual == expected\n"
               "d=json.load(sys.stdin)\nnamespace={}\n"
               "exec(compile(d['code'],'<trial-artifact>','exec'),namespace)\n"
               "f=namespace[d['function']]\n"
               "results=[]\nfor c in d['cases']:\n"
               "    actual=f(*c['args'])\n"
               "    results.append(equal(actual, c['expected']))\n"
               "print(json.dumps(results))\nraise SystemExit(0 if all(results) else 1)\n")
    payload = {"code": artifacts[spec["path"]].decode(), "function": spec["function"], "cases": spec["cases"]}
    try:
        with tempfile.TemporaryDirectory(prefix="company-outcome-oracle-") as scratch:
            result = subprocess.run([sys.executable, "-I", "-B", "-c", program], input=encode(payload),
                                    capture_output=True, text=True, timeout=5, cwd=scratch,
                                    env={"PATH": os.defpath, "PYTHONHASHSEED": "0"})
    except subprocess.TimeoutExpired:
        return {**check, "reason": "oracle timeout", "exit_code": None}
    try:
        case_results = decode(result.stdout)
    except ValueError:
        case_results = None
    return {**check, "passed": result.returncode == 0 and not critical and
            case_results == [True] * len(spec["cases"]),
            "exit_code": result.returncode, "stdout": result.stdout[:4000], "stderr": result.stderr[:4000],
            "reason": "isolated Python function cases; no provider or device execution"}


def trial_status(reported, execution_info, checks, reviewed_critical, trace_present):
    """Pure classification shared by saved grading and accepted-report validation."""
    critical = checks['critical_failure'] or reviewed_critical is True
    if critical or execution_info['outcome'] == 'failed':
        status = 'failure'
    elif reported in {'failure', 'environment_failure', 'aborted'}:
        status = reported
    elif execution_info['outcome'] is None or checks.get('reason') in {'oracle timeout', 'task code execution not enabled'}:
        status = 'unknown'
    elif not checks['passed']:
        status = 'failure'
    elif reported == 'unknown' or reviewed_critical is None or not trace_present or execution_info['modified_artifacts'] is None:
        status = 'unknown'
    else:
        status = 'success'
    return status, True if critical else reviewed_critical


def score(args):
    root, plan = load_plan(args.plan, args.plan_sha256)
    expected = {t["id"]: t for t in plan["expected_trials"]}
    actual, attempts = {}, set()
    trials_dir = root / "trials"
    dirs = sorted(trials_dir.iterdir()) if trials_dir.exists() else []
    for directory in dirs:
        require(directory.name in expected and directory.is_dir() and not directory.is_symlink(), "unknown trial directory")
        tid, trial = directory.name, expected[directory.name]
        record = decode(read_local(root, "trials/" + tid + "/record.json"))
        shape(record, {"format", "binding", "reported_status", "workspace", "artifacts",
                       "launch", "worker_done", "brief", "trace", "usage"}, "trial record")
        require(record["format"] == VERSION, "unsupported trial record")
        require(record["binding"] == trial_binding(plan, args.plan_sha256, trial), "stale/wrong candidate trial binding")
        require(record["reported_status"] in STATUSES, "invalid reported status")
        require(bound(root, record["brief"]) == brief(root, plan, args.plan_sha256, trial, Path(record["workspace"])).encode(),
                "submitted brief mismatch")
        require(isinstance(record["artifacts"], dict), "artifacts required")
        artifacts = {local_name(name): bound(root, ref) for name, ref in record["artifacts"].items()}
        snapshot = file_tree(root / "trials" / tid / "artifacts")
        require(snapshot == artifacts, "artifact inventory mismatch")
        execution_info = execution(root, record, plan, attempts)
        changed = sorted(name for name, data in artifacts.items()
                         if name not in plan["tasks"][trial["task"]]["initial"] or
                         data != plan["tasks"][trial["task"]]["initial"][name].encode())
        changed += sorted(set(plan["tasks"][trial["task"]]["initial"]) - set(artifacts))
        if execution_info["modified_artifacts"] is not None:
            require(execution_info["modified_artifacts"] == sorted(changed), "worker_done/artifact path binding mismatch")
        checks = oracle(plan["tasks"][trial["task"]], artifacts, args.allow_task_code)
        review_path = directory / "review.json"
        reviewed_critical = None
        if review_path.exists():
            review = decode(read_local(root, "trials/" + tid + "/review.json"))
            template = review_binding(record, execution_info, plan["evidence_class"])
            shape(review, template, "independent review")
            require(all(review[k] == template[k] for k in template
                        if k not in {"assessor", "critical_failure", "basis", "note"}), "stale review binding")
            text(review["assessor"], "assessor")
            text(review["note"], "review note")
            require(review["assessor"] != execution_info["executor"], "self review refused")
            require(review["basis"] == ("independent" if plan["evidence_class"] == "real" else "synthetic_fixture"),
                    "synthetic/real review mismatch")
            require(review["critical_failure"] is None or type(review["critical_failure"]) is bool,
                    "critical failure must be boolean/null")
            reviewed_critical = review["critical_failure"]
        if record["trace"] is not None:
            bound(root, record["trace"])
        usage = None
        if record["usage"] is not None:
            usage = decode(bound(root, record["usage"]))
            shape(usage, {"coverage", "raw_total", "tokenizer", "scope", "source"}, "usage")
            require(usage["coverage"] in {"unknown", "partial", "complete"}, "invalid usage coverage")
            require(usage["raw_total"] is None or type(usage["raw_total"]) is int and usage["raw_total"] >= 0,
                    "invalid raw usage")
            for key in ("tokenizer", "scope", "source"):
                require(usage[key] is None or isinstance(usage[key], str), "invalid usage field")
        reported = record["reported_status"]
        status, critical = trial_status(reported, execution_info, checks, reviewed_critical,
                                        record['trace'] is not None)
        actual[tid] = {"status": status, "execution": execution_info, "oracle": checks,
                       "reported_status": reported,
                       "critical_failure": critical,
                       "usage": usage, "record_sha256": sha(read_local(root, "trials/" + tid + "/record.json")),
                       "review_sha256": sha(read_local(root, "trials/" + tid + "/review.json")) if review_path.exists() else None}
    return summarize(plan, args.plan_sha256, actual)


def summarize(plan, plan_sha256, actual):
    """Pure full report construction; no oracle, file IO or task execution."""
    expected = {t['id']: t for t in plan['expected_trials']}
    arms = {}
    for arm in plan["arms"]:
        tasks = []
        for task in plan["tasks"]:
            ids = [t["id"] for t in expected.values() if t["arm"] == arm and t["task"] == task]
            counts = Counter(actual[t]["status"] if t in actual else "missing" for t in ids)
            complete, successes, n = not counts["missing"] and not counts["unknown"], counts["success"], len(ids)
            tasks.append({"task": task, "planned": n, "counts": dict(sorted(counts.items())),
                          "confirmed_success_lower_bound": successes / n,
                          "success_rate": successes / n if complete else None,
                          "all_success_k": comb(successes, plan["pass_k"]) / comb(n, plan["pass_k"])
                          if complete and n >= plan["pass_k"] else None})
        rates = [t["success_rate"] for t in tasks]
        arms[arm] = {"tasks": tasks, "task_macro_success": sum(rates) / len(rates) if None not in rates else None}
    criticals = sorted(t for t, v in actual.items() if v["critical_failure"] is True)
    missing = sorted(set(expected) - set(actual))
    return {"format": VERSION, "evidence_class": plan["evidence_class"], "plan_sha256": plan_sha256,
            "study": "feasibility", "planned_attempts": len(expected), "observed_attempts": len(actual),
            "missing_trials": missing, "critical_failure_trials": criticals, "trials": actual, "arms": arms,
            "gate": "critical_failure" if criticals else "incomplete" if missing or any(
                v["status"] == "unknown" or v["critical_failure"] is None for v in actual.values())
                else "recorded_outcomes_graded",
            "quality": None, "user_burden": None,
            "tokens": {"total_raw_tokens": None, "coverage": "unknown",
                       "reason": "Per-trial available raw usage retained; lead, retries, review, integration and overlap not certified."},
            "comparison": {"statistical_superiority": None, "reason": "Small feasibility pilot; no effects inference."},
            "limits": ["Saved-byte hashes and supplied receipts do not authenticate origin, identity, independence or tool authority.",
                       "Submitted brief binding is a collector declaration; Orca launch does not attest prompt bytes.",
                       "Host/global instructions and hooks are common uncontrolled context; supplied-instruction comparison only.",
                       "Deterministic source tests, real saved executions and installed effects are separate evidence tiers.",
                       "No scheduling, launch, retry, publication, deployment, promotion or acceptance authority."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    freeze_parser = commands.add_parser("freeze", help="Create a new hash-anchored feasibility bundle")
    for name in ("spec", "baseline", "candidate", "context", "out"):
        freeze_parser.add_argument("--" + name, type=Path, required=True)
    for name in ("source-commit", "agent", "model"):
        freeze_parser.add_argument("--" + name, required=True)
    freeze_parser.add_argument("--effort", help="Observed supported effort; omit only when unsupported (frozen null)")
    freeze_parser.add_argument("--tasks")
    freeze_parser.add_argument("--repeats", type=int, default=2)
    freeze_parser.add_argument("--evidence-class", choices=("synthetic", "real"), default="real")
    for name in ("prepare", "collect", "score"):
        child = commands.add_parser(name)
        child.add_argument("--plan", type=Path, required=True)
        child.add_argument("--plan-sha256", required=True)
        if name != "score":
            child.add_argument("--trial", required=True)
            child.add_argument("--workspace", type=Path, required=True)
        if name == "collect":
            for field in ("brief", "launch", "done", "trace", "usage"):
                child.add_argument("--" + field, type=Path, required=field in {"brief", "launch"})
            child.add_argument("--status", choices=sorted(STATUSES), default="success")
        if name == "score":
            child.add_argument("--allow-task-code", action="store_true",
                               help="Execute saved trusted Python task artifacts in a temporary cwd; not a sandbox")
    args = parser.parse_args(argv)
    try:
        result = {"freeze": freeze, "prepare": prepare, "collect": collect, "score": score}[args.command](args)
        print(encode(result), end="")
        return 0
    except (Invalid, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        print(encode({"format": VERSION, "status": "invalid", "error": str(exc)}), end="")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
