#!/usr/bin/env python3
"""Offline MVP: extract deterministic failed->repair->success candidates.

Usage:
  python3 tools/cowpath_mvp.py data/all_sessions.txt -o data/mvp.json
  python3 tools/cowpath_mvp.py data/all_sessions.txt --markdown data/mvp.md

No LLM calls. Input is one absolute session.jsonl.zstd path per line.
"""
from __future__ import annotations
import argparse, hashlib, json, re, subprocess
from collections import Counter, defaultdict
from pathlib import Path

SELF_FIXING = ("read the file", "re-read", "narrow pattern", "provide a more specific",
               "must be a number", "positive number", "current is")
ENV = ("timed out", "timeout", "429", "rate_limit", "502", "500", "overloaded",
       "stream idle", "upstream", "no cluster", "econn", "network")
NOISE = ("sandbox escalation", "invalid justification", "not strictly wider", "sandbox:")
PATH_RE = re.compile(r"(?<![\w-])/(?:[^\s\"']+)")


def text_of(v):
    if isinstance(v, str): return v
    if isinstance(v, list): return " ".join(text_of(x) for x in v)
    if isinstance(v, dict):
        if v.get("type") == "text": return v.get("text", "")
        if v.get("type") == "tool-result": return text_of(v.get("content"))
        return " ".join(text_of(x) for x in v.values())
    return ""


def norm_error(s):
    s = re.sub(r"/[^\s\"']+", "<path>", s[:240])
    s = re.sub(r"\b\d+(?:\.\d+)?\b", "<num>", s)
    return re.sub(r"\s+", " ", s).strip()[:180]


def classify_error(s):
    x = s.lower()
    if any(k in x for k in NOISE): return "session-noise"
    if any(k in x for k in ENV): return "env"
    if any(k in x for k in SELF_FIXING): return "self-fixing"
    if any(k in x for k in ("interrupted", "aborted", "cancelled", "partial output", "unknown")): return "opaque"
    return "candidate"


def args_text(data):
    for key in ("arguments", "args", "input", "params"):
        if key in data: return text_of(data[key])
    return ""


def objects(name, data, result=""):
    """Extract stable path/object keys from call arguments and result text."""
    blob = " ".join((name, args_text(data), result))
    paths = []
    for p in PATH_RE.findall(blob):
        p = p.rstrip(",.;:)]}")
        if p.startswith("//") or p.startswith("/http") or len(p) >= 500: continue
        if p not in paths: paths.append(p)
    if paths: return paths
    # Non-file targets remain useful, but avoid using the tool name alone as identity.
    for key in ("url", "query", "task", "target", "command"):
        val = data.get(key)
        if isinstance(val, str) and val.strip(): return [f"{key}:{val.strip()[:180]}"]
    return []


def read_session(path):
    raw = subprocess.run(["zstd", "-d", "-c", str(path)], check=False,
                         capture_output=True, text=True).stdout
    events = []
    meta = {}
    for line in raw.splitlines():
        try: event = json.loads(line)
        except json.JSONDecodeError: continue
        typ, data = event.get("type"), event.get("data", {}) or {}
        if typ in ("permission/preset", "sandbox/mode", "approval/policy"):
            meta[typ] = data
        if typ == "tool/call":
            events.append({"kind":"call", "turn":data.get("turn"), "step":data.get("step"),
                           "name":data.get("name","?"), "data":data,
                           "call_id":data.get("callId"), "ok":None, "result":""})
        elif typ == "tool/result":
            key = (data.get("turn"), data.get("step"))
            for rec in reversed(events):
                if rec["kind"] == "call" and (rec["turn"], rec["step"]) == key and rec["ok"] is None:
                    content = data.get("message", {}).get("content", [])
                    rec["result"] = text_of(content)
                    rec["ok"] = not any(isinstance(c, dict) and c.get("type") == "tool-result" and c.get("isError") for c in content)
                    break
    return meta, events


def scan(paths):
    candidates = defaultdict(lambda: {"sessions": set(), "failures": Counter(), "repairs": Counter(), "examples": []})
    summary = Counter(sessions=0, calls=0, errors=0, filtered=0, candidates=0, paired=0)
    for path in paths:
        if not path: continue
        meta, events = read_session(path)
        summary["sessions"] += 1
        summary["calls"] += sum(e["kind"] == "call" for e in events)
        # State is local to this session by construction.
        for i, rec in enumerate(events):
            if rec["kind"] != "call" or rec["ok"] is not False: continue
            summary["errors"] += 1
            err = rec["result"]
            cls = classify_error(err)
            if cls != "candidate": summary["filtered"] += 1; continue
            objs = objects(rec["name"], rec["data"], err)
            if not objs: continue
            # Look forward in same session for a successful action on same object.
            for obj in objs:
                matches = []
                for nxt in events[i+1:]:
                    if nxt["kind"] != "call" or nxt["ok"] is not True: continue
                    if obj in objects(nxt["name"], nxt["data"], nxt["result"]):
                        matches.append(nxt)
                if not matches: continue
                # Prefer successful retry of the failed tool; otherwise retain the
                # first successful same-object action as a cross-tool repair.
                success = next((x for x in matches if x["name"] == rec["name"]), matches[0])
                summary["paired"] += 1
                key = (obj, norm_error(err))
                c = candidates[key]
                c["sessions"].add(Path(path).parent.name)
                c["failures"][rec["name"]] += 1
                c["repairs"][success["name"]] += 1
                if len(c["examples"]) < 3:
                    c["examples"].append({"session":Path(path).parent.name, "failure_tool":rec["name"], "repair_tool":success["name"], "error":err[:500]})
    out=[]
    for (obj, sig), c in sorted(candidates.items(), key=lambda kv:(-len(kv[1]["sessions"]), -sum(kv[1]["failures"].values()), kv[0])):
        out.append({"object":obj, "failure_signature":sig, "session_count":len(c["sessions"]),
                    "sessions":sorted(c["sessions"]), "failure_tools":dict(c["failures"]),
                    "repair_tools":dict(c["repairs"]), "examples":c["examples"]})
    summary["candidates"] = len(out)
    return {"schema":"cowpath-mvp/v1", "summary":dict(summary), "candidates":out}


def markdown(report):
    s=report["summary"]; lines=["# Cowpath MVP 候选报告", "", f"会话 {s['sessions']}；tool 调用 {s['calls']}；错误 {s['errors']}；过滤 {s['filtered']}；配对 {s['paired']}；候选 {s['candidates']}。", ""]
    for i,c in enumerate(report["candidates"],1):
        lines += [f"## {i}. `{c['object']}`", "", f"- 失败：`{c['failure_signature']}`", f"- 独立会话：{c['session_count']}", f"- 失败工具：{c['failure_tools']}", f"- 修正工具：{c['repair_tools']}", ""]
    return "\n".join(lines)


def main():
    ap=argparse.ArgumentParser(description="Offline cowpath historical-session Skill reviewer")
    ap.add_argument("list_file", nargs="?", type=Path, help="session list for scan mode")
    ap.add_argument("-o", "--output", type=Path)
    ap.add_argument("--markdown", type=Path)
    ap.add_argument("--workspace", type=Path, help="review a workspace and discover its historical sessions")
    ap.add_argument("--sessions-root", type=Path)
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--proposals-only", action="store_true", help="print proposals without writing")
    a=ap.parse_args()
    if a.workspace:
        report=review_workspace(a.workspace, a.sessions_root, a.limit, a.proposals_only)
    else:
        if not a.list_file: ap.error("provide list_file or --workspace")
        paths=[x.strip() for x in a.list_file.read_text().splitlines() if x.strip() and not x.lstrip().startswith("#")]
        report=scan(paths)
    payload=json.dumps(report, ensure_ascii=False, indent=2)
    if a.output: a.output.write_text(payload+"\n")
    else: print(payload)
    if a.markdown: a.markdown.write_text(markdown(report)+"\n")


# --- workspace review / installable offline flow ---
def discover_sessions(workspace, sessions_root=None):
    """Find DSH sessions for an encoded workspace directory."""
    workspace = str(Path(workspace).resolve())
    root = Path(sessions_root or Path.home()/".dsh"/"sessions")
    encoded = "--" + workspace.strip("/").replace("/", "-") + "--"
    candidates = [root/encoded]
    # Also accept direct project directory names supplied by callers.
    candidates.append(root/workspace.replace("/", "-"))
    for base in candidates:
        if base.exists():
            return sorted(base.glob("session-*/session.jsonl.zstd"))
    return []


def existing_skills(workspace):
    root = Path(workspace) / ".agents" / "skills"
    return sorted(p for p in root.glob("*/SKILL.md") if p.is_file())


def skill_terms(path):
    text = path.read_text(errors="replace")[:12000].lower()
    words = set(re.findall(r"[a-z][a-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}", text))
    return words


def suggest_skill(candidate, skills):
    """Deterministic overlap suggestion; model-free and explainable."""
    hay = (candidate["object"] + " " + candidate["failure_signature"]).lower()
    tokens = set(re.findall(r"[a-z][a-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}", hay))
    best, score, overlap = None, 0, set()
    for path in skills:
        hit = tokens & skill_terms(path)
        if len(hit) > score:
            best, score, overlap = path, len(hit), hit
    return {"action": "fuse" if score else "new", "skill": str(best) if best else None,
            "overlap": sorted(overlap)}


def skill_draft(candidate):
    obj = candidate["object"]
    sig = candidate["failure_signature"]
    repairs = ", ".join(f"{k} ({v})" for k,v in candidate["repair_tools"].items())
    return f"""---\nname: cowpath-{hashlib.sha1((obj+sig).encode()).hexdigest()[:10]}\ndescription: Prevent and recover from `{sig}` on `{obj}` based on historical workspace sessions.\nmetadata:\n  source: cowpath-offline\n  evidence_sessions: {candidate['session_count']}\n---\n\n# Recovered path\n\n## Trigger\n\nA `{sig}` failure occurs while operating on `{obj}`.\n\n## Recovery\n\nUse the successful historical recovery actions: {repairs}. Re-read the current target before retrying when the target may have changed.\n\n## Evidence\n\n- Independent sessions: {candidate['session_count']}\n- Failure tools: {candidate['failure_tools']}\n- Repair tools: {candidate['repair_tools']}\n- Source session IDs: {', '.join(candidate['sessions'])}\n\nThis skill was proposed by cowpath and requires human review before use.\n"""


def apply_decision(candidate, suggestion, workspace, choice):
    root = Path(workspace) / ".agents" / "skills"
    root.mkdir(parents=True, exist_ok=True)
    draft = skill_draft(candidate)
    if choice == "n":
        name = "cowpath-" + hashlib.sha1((candidate["object"] + candidate["failure_signature"]).encode()).hexdigest()[:10]
        target = root / name / "SKILL.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(draft)
        return f"created {target}"
    if choice == "f" and suggestion.get("skill"):
        target = Path(suggestion["skill"])
        original = target.read_text(errors="replace")
        backup = target.with_suffix(target.suffix + ".cowpath.bak")
        backup.write_text(original)
        section = "\n\n## Cowpath recovered path\n\n" + draft.split("---\n", 2)[-1]
        target.write_text(original.rstrip() + section)
        return f"fused into {target} (backup: {backup})"
    return "ignored"


def review_workspace(workspace, sessions_root=None, limit=20, non_interactive=False):
    paths = discover_sessions(workspace, sessions_root)
    report = scan([str(p) for p in paths])
    skills = existing_skills(workspace)
    report["workspace"] = str(Path(workspace).resolve())
    report["session_paths"] = [str(p) for p in paths]
    report["proposals"] = []
    for candidate in report["candidates"][:limit]:
        suggestion = suggest_skill(candidate, skills)
        proposal = dict(candidate, suggestion=suggestion, decision="pending")
        if non_interactive:
            report["proposals"].append(proposal)
            continue
        print("\n--- Cowpath proposal ---")
        print(f"Object: {candidate['object']}\nFailure: {candidate['failure_signature']}")
        print(f"Evidence: {candidate['session_count']} sessions; repairs: {candidate['repair_tools']}")
        if suggestion["action"] == "fuse": print(f"Suggested: fuse into {suggestion['skill']} (overlap: {suggestion['overlap']})")
        else: print("Suggested: create a new skill")
        while True:
            choice = input("[n]ew  [f]use  [s]kip  [q]uit: ").strip().lower() or "s"
            if choice in "nfsq": break
        if choice == "q": break
        proposal["decision"] = {"n":"new", "f":"fuse", "s":"skip"}[choice]
        if choice in ("n", "f"):
            print(apply_decision(candidate, suggestion, workspace, choice))
        report["proposals"].append(proposal)
    return report


if __name__ == "__main__": main()
