#!/usr/bin/env python3
"""Rank tool-error families by what it cost the agent to recover from them.

Usage:
  python3 tools/recovery_cost.py data/all_sessions.txt -o data/recovery_cost.json
  python3 tools/recovery_cost.py data/all_sessions.txt --markdown data/recovery_cost.md

No LLM calls. Input is one absolute session.jsonl.zstd path per line.

For each failed tool call F, recovery R is the first later successful call in
the same turn with the same tool and the same target (file path, or exact
command for bash); if none, the first later successful same-tool call in the
same turn. Costs are measured between F and R:
  extra_steps   R.step - F.step (LLM round trips spent getting back on track)
  extra_calls   tool calls issued after F up to and including R
  extra_input / extra_output  token usage of steps F.step+1 .. R.step
Failures with no recovery in the same turn are counted as unrecovered.
loop_turns counts turns where one family failed at least LOOP_MIN times, the
signature of an agent stuck retrying the same mistake.
The step/token numbers are upper bounds: intermediate steps may also do useful
work unrelated to the failure.
"""
from __future__ import annotations
import argparse, hashlib, json, re, subprocess
from collections import defaultdict
from pathlib import Path

SCHEMA = "cowpath-recovery-cost/v1"
LOOP_MIN = 3

# Ordered (family, substring) rules over the lower-cased error text.
FAMILIES = (
    ("sandbox/escalation-not-wider", "not strictly wider"),
    ("sandbox/justification-invalid", "invalid justification"),
    ("sandbox/escalation-args", "invalid escalation"),
    ("fs/edit-before-read", "requires reading"),
    ("fs/stale-since-read", "changed since it was read"),
    ("fs/gone-since-read", "no longer exists"),
    ("fs/old-string-not-found", "old_string was not found"),
    ("fs/old-string-ambiguous", "old_string appears"),
    ("fs/read-not-found", "cannot read"),
    ("fs/offset-out-of-range", "is out of range for"),
    ("grep/output-cap", "more raw output than"),
    ("args/invalid", "invalid arguments"),
    ("subagent/max-depth", "exceeds maxdepth"),
    ("run/aborted", "aborted"),
    ("run/timed-out", "timed out"),
)


def text_of(v):
    if isinstance(v, str): return v
    if isinstance(v, list): return " ".join(text_of(x) for x in v)
    if isinstance(v, dict):
        if v.get("type") == "text": return v.get("text", "")
        if v.get("type") == "tool-result": return text_of(v.get("content"))
        return " ".join(text_of(x) for x in v.values())
    return ""


def norm_error(s):
    s = re.sub(r"\"[^\"]*\"", "<str>", s[:240])
    s = re.sub(r"/[^\s\"']+", "<path>", s)
    s = re.sub(r"\b\d+(?:\.\d+)?\b", "<num>", s)
    return re.sub(r"\s+", " ", s).strip()[:160]


def family(err):
    x = err.lower()
    for name, needle in FAMILIES:
        if needle in x: return name
    return "other:" + norm_error(err)


def parse_args(raw):
    if isinstance(raw, dict): return raw
    try:
        val = json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return val if isinstance(val, dict) else {}


def target(name, args):
    for key in ("file_path", "path", "filePath"):
        if isinstance(args.get(key), str): return f"path:{args[key]}"
    if name == "bash" and isinstance(args.get("command"), str):
        return "cmd:" + args["command"].strip()
    return None


def read_session(path):
    raw = subprocess.run(["zstd", "-d", "-c", str(path)], check=False,
                         capture_output=True, text=True).stdout
    calls, by_id, usage, models = [], {}, defaultdict(lambda: [0, 0]), {}
    for line in raw.splitlines():
        try: event = json.loads(line)
        except json.JSONDecodeError: continue
        typ, data = event.get("type"), event.get("data") or {}
        if typ == "tool/call":
            args = parse_args(data.get("arguments"))
            rec = {"turn": data.get("turn"), "step": data.get("step"), "name": data.get("name", "?"),
                   "target": target(data.get("name"), args), "ok": None, "error": ""}
            calls.append(rec)
            by_id[data.get("callId")] = rec
        elif typ == "tool/result":
            msg = data.get("message") or {}
            rec = by_id.get((msg.get("source") or {}).get("callId"))
            if rec is None or rec["ok"] is not None: continue
            content = msg.get("content") or []
            failed = any(isinstance(c, dict) and c.get("type") == "tool-result" and c.get("isError") for c in content)
            rec["ok"] = not failed
            if failed: rec["error"] = text_of(content)
        elif typ == "assistant/message":
            u = data.get("usage") or {}
            acc = usage[(data.get("turn"), data.get("step"))]
            acc[0] += int(u.get("inputTokens") or 0)
            acc[1] += int(u.get("outputTokens") or 0)
            src = (data.get("message") or {}).get("source") or {}
            models[(data.get("turn"), data.get("step"))] = src.get("model") or "?"
    for rec in calls:
        rec["model"] = models.get((rec["turn"], rec["step"]), "?")
    return calls, usage


def recovery(calls, i):
    fail = calls[i]
    same_tool = None
    for nxt in calls[i + 1:]:
        if nxt["turn"] != fail["turn"]: break
        if nxt["ok"] is not True or nxt["name"] != fail["name"]: continue
        if fail["target"] and nxt["target"] == fail["target"]: return nxt, "same-target"
        if same_tool is None: same_tool = nxt
    return (same_tool, "same-tool") if same_tool else (None, None)


def scan(paths):
    fams = defaultdict(lambda: {"errors": 0, "recovered": 0, "same_target": 0, "sessions": set(),
                                "tools": defaultdict(int), "extra_steps": 0, "extra_calls": 0,
                                "extra_input": 0, "extra_output": 0, "example": "",
                                "models": defaultdict(int), "loop_turns": 0, "max_per_turn": 0})
    total = {"sessions": 0, "calls": 0, "errors": 0, "input_tokens": 0, "output_tokens": 0}
    for path in paths:
        calls, usage = read_session(path)
        total["sessions"] += 1
        total["calls"] += len(calls)
        total["input_tokens"] += sum(v[0] for v in usage.values())
        total["output_tokens"] += sum(v[1] for v in usage.values())
        # All state above is local to this session.
        per_turn = defaultdict(int)
        for i, fail in enumerate(calls):
            if fail["ok"] is not False: continue
            total["errors"] += 1
            f = fams[family(fail["error"])]
            f["errors"] += 1
            f["sessions"].add(path)
            f["tools"][fail["name"]] += 1
            f["models"][fail["model"]] += 1
            per_turn[(family(fail["error"]), fail["turn"])] += 1
            if not f["example"]: f["example"] = fail["error"][:300]
            rec, how = recovery(calls, i)
            if rec is None: continue
            f["recovered"] += 1
            f["same_target"] += how == "same-target"
            f["extra_steps"] += rec["step"] - fail["step"]
            f["extra_calls"] += calls.index(rec) - i
            for step in range(fail["step"] + 1, rec["step"] + 1):
                u = usage.get((fail["turn"], step), (0, 0))
                f["extra_input"] += u[0]
                f["extra_output"] += u[1]
        for (name, _turn), n in per_turn.items():
            fams[name]["loop_turns"] += n >= LOOP_MIN
            fams[name]["max_per_turn"] = max(fams[name]["max_per_turn"], n)
    rows = []
    for name, f in fams.items():
        r = f["recovered"] or 1
        rows.append({"family": name, "errors": f["errors"], "sessions": len(f["sessions"]),
                     "tools": dict(sorted(f["tools"].items())),
                     "models": dict(sorted(f["models"].items())),
                     "loop_turns": f["loop_turns"], "max_per_turn": f["max_per_turn"],
                     "recovered": f["recovered"], "unrecovered": f["errors"] - f["recovered"],
                     "same_target_recoveries": f["same_target"],
                     "extra_steps": f["extra_steps"], "extra_calls": f["extra_calls"],
                     "extra_input_tokens": f["extra_input"], "extra_output_tokens": f["extra_output"],
                     "steps_per_recovery": round(f["extra_steps"] / r, 2),
                     "input_tokens_per_recovery": round(f["extra_input"] / r),
                     "example": f["example"]})
    rows.sort(key=lambda x: (-x["extra_input_tokens"], -x["errors"], x["family"]))
    return {"schema": SCHEMA, "summary": total, "families": rows}


def provenance(list_file, paths):
    script = Path(__file__).resolve()
    commit = subprocess.run(["git", "-C", str(script.parent), "rev-parse", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    return {"manifest_sha256": hashlib.sha256(Path(list_file).read_bytes()).hexdigest(),
            "script_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
            "git_commit": commit or None, "manifest_paths": len(paths)}


def markdown(report):
    s = report["summary"]
    lines = ["# 报错恢复成本排序", "",
             f"会话 {s['sessions']}；tool 调用 {s['calls']}；报错 {s['errors']}；"
             f"全部 input tokens {s['input_tokens']:,}；output tokens {s['output_tokens']:,}。", "",
             "| 家族 | 报错 | 会话 | 恢复 | 未恢复 | 死循环 turn | 单 turn 最多 | 额外步数 | 步/次 | 额外 input tokens | 额外 output tokens |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in report["families"]:
        if r["errors"] < 3: continue
        lines.append(f"| `{r['family'][:70]}` | {r['errors']} | {r['sessions']} | {r['recovered']} | {r['unrecovered']} | {r['loop_turns']} | {r['max_per_turn']} | "
                     f"{r['extra_steps']} | {r['steps_per_recovery']} | {r['extra_input_tokens']:,} | {r['extra_output_tokens']:,} |")
    lines += ["", f"死循环 turn：同一 turn 内同一家族报错 ≥ {LOOP_MIN} 次。报错少于 3 次的家族只在 JSON 里。额外步数与 tokens 是上界。"]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Rank tool-error families by recovery cost")
    ap.add_argument("list_file", type=Path, help="one session.jsonl.zstd path per line")
    ap.add_argument("-o", "--output", type=Path)
    ap.add_argument("--markdown", type=Path)
    a = ap.parse_args()
    paths = [x.strip() for x in a.list_file.read_text().splitlines() if x.strip() and not x.lstrip().startswith("#")]
    report = scan(paths)
    report["provenance"] = provenance(a.list_file, paths)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if a.output: a.output.write_text(payload + "\n")
    else: print(payload)
    if a.markdown: a.markdown.write_text(markdown(report) + "\n")


if __name__ == "__main__": main()
