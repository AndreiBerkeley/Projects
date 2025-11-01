#!/usr/bin/env python3
"""
Manual failure mode annotations using custom taxonomy.
Logic-based analysis (no LLM calls).
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List

# ---------- Configuration ----------
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "processed"
OUTPUTS_DIR = ROOT / "outputs"
ANALYSIS_DIR = OUTPUTS_DIR / "analysis"
TRACES_DIR = OUTPUTS_DIR / "traces"

DATASET_PATH = DATA_DIR / "olympiadbench_test_sampled_50.json"
AGENT_EVAL_PATH = ANALYSIS_DIR / "agent_evaluation.json"
PREDICTIONS_PATH = OUTPUTS_DIR / "agents" / "predictions_sample50_mt.json"
OUTPUT_PATH = ANALYSIS_DIR / "manual_annotations.json"

# ---------- Utilities ----------
def load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"Missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))

def save_json(data: Any, path: Path):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved: {path}")

# ---------- Trace Loading ----------
def load_trace(trace_file: str) -> List[Dict]:
    """Load trace file as list of events."""
    p = Path(trace_file)
    if not p.exists():
        return []
    
    events = []
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    events.append(json.loads(line))
                except:
                    pass
    return events

# ---------- Trace Analysis Helpers ----------
def get_agent_sequence(trace: List[Dict]) -> List[str]:
    """Extract ordered list of agents that executed."""
    seq = []
    for event in trace:
        agent = event.get("agent")
        if agent and agent != "system":
            seq.append(agent)
    return seq

def find_solver_answer(trace: List[Dict]) -> str:
    """Extract solver's final answer."""
    for event in trace:
        if event.get("agent") == "solver" and event.get("event") == "final_extracted":
            return event.get("data", {}).get("final_answer", "") or ""
    
    # Fallback: check completion_received
    for event in trace:
        if event.get("agent") == "solver" and event.get("event") == "completion_received":
            content = event.get("data", {}).get("content_head", "") or ""
            return content[:100]  # Return snippet
    
    return ""

def find_refiner_answer(trace: List[Dict]) -> str:
    """Extract refiner's final answer."""
    for event in trace:
        if event.get("agent") == "refiner" and event.get("event") == "final_extracted":
            return event.get("data", {}).get("final_answer", "") or ""
    
    # Fallback: check completion_received
    for event in trace:
        if event.get("agent") == "refiner" and event.get("event") == "completion_received":
            content = event.get("data", {}).get("content_head", "") or ""
            return content[:100]
    
    return ""

def find_checker_verdict(trace: List[Dict]) -> str:
    """Extract checker's verdict (ACCEPT/REJECT)."""
    verdict = ""
    for event in trace:
        if event.get("agent") == "checker" and event.get("event") == "verdict":
            verdict = event.get("data", {}).get("verdict", "") or verdict
    return verdict

def find_arbiter_choice(trace: List[Dict]) -> str:
    """Extract arbiter's chosen answer."""
    choice = ""
    for event in trace:
        if event.get("agent") == "arbiter" and event.get("event") == "decision":
            choice = event.get("data", {}).get("chosen", "") or choice
    return choice

def has_run_end(trace: List[Dict]) -> bool:
    """Check if pipeline completed normally."""
    return any(event.get("event") == "run_end" for event in trace)

def normalize_answer(ans: str) -> str:
    """Normalize answer for comparison."""
    import re
    if not ans:
        return ""
    ans = str(ans).strip()
    ans = re.sub(r'\\text\{([^}]+)\}', r'\1', ans)
    ans = re.sub(r'\\boxed\{([^}]+)\}', r'\1', ans)
    ans = ans.replace('$', '').replace('\\', '').replace(' ', '')
    ans = ans.replace('{', '').replace('}', '')
    return ans.lower()

def answers_match(ans1: str, ans2: list) -> bool:
    """Check if answers match."""
    if not ans1:
        return False
    if isinstance(ans2, str):
        ans2 = [ans2]
    
    ans1_norm = normalize_answer(ans1)
    for a in ans2:
        if normalize_answer(str(a)) == ans1_norm:
            return True
    return False

# ---------- Manual Failure Mode Analysis ----------
def analyze_trace_manually(
    problem_id: str,
    trace: List[Dict],
    success: bool,
    pred_ans: str,
    gt_ans: list,
    problem_text: str
) -> Dict[str, Any]:
    """
    Analyze trace using custom failure mode taxonomy.
    
    Categories:
    1. Agent Orchestration Errors
       1.1 Improper Agent Order
       1.2 Missing Required Agent
       1.4 Premature Termination
    
    2. Agent Output Errors
       2.1 Solver Failure
       2.2 Checker Indecisiveness
       2.3 Refiner No-Op
       2.4 Arbiter Indecisiveness
    
    3. Verification Errors
       3.1 Checker False Acceptance
       3.2 Checker False Rejection
    
    4. Coordination Errors
       4.1 Refiner Degradation
       4.2 Arbiter Poor Decision
       4.3 Coordination Failure (Meta)
    
    5. Answer Quality Errors
       5.1 Computational Error
    """
    failure_modes: Dict[str, Dict[str, str]] = {}
    summary_points: List[str] = []
    
    # Extract trace information
    agent_sequence = get_agent_sequence(trace)
    num_agents = len(set(agent_sequence))
    
    solver_ans = find_solver_answer(trace)
    refiner_ans = find_refiner_answer(trace)
    verdict = find_checker_verdict(trace)
    arbiter_pick = find_arbiter_choice(trace)
    ended = has_run_end(trace)
    
    # ----- CATEGORY 1: Agent Orchestration Errors -----
    
    # 1.1 Improper Agent Order
    order_issues = []
    first_pos = {}
    for i, agent in enumerate(agent_sequence):
        if agent not in first_pos:
            first_pos[agent] = i
    
    if "checker" in first_pos and "solver" in first_pos:
        if first_pos["checker"] < first_pos["solver"]:
            order_issues.append("checker executed before solver")
    
    if "refiner" in first_pos and "checker" in first_pos:
        if first_pos["refiner"] < first_pos["checker"]:
            order_issues.append("refiner executed before checker")
    
    if order_issues:
        failure_modes["1.1"] = {
            "name": "Improper Agent Order",
            "definition": "Agents execute in illogical sequence (e.g., checker before solver).",
            "example_from_trace": "; ".join(order_issues)
        }
        summary_points.append("Improper agent order")
    
    # 1.2 Missing Required Agent
    checker_rejected = (verdict == "REJECT")
    if checker_rejected and "refiner" not in agent_sequence:
        failure_modes["1.2"] = {
            "name": "Missing Required Agent",
            "definition": "Expected agent didn't run when it should have (e.g., no refiner after REJECT).",
            "example_from_trace": f"Checker verdict={verdict} but refiner never executed"
        }
        summary_points.append("Missing refiner after rejection")
    
    # 1.4 Premature Termination
    if not ended or pred_ans == "":
        failure_modes["1.4"] = {
            "name": "Premature Termination",
            "definition": "Pipeline stops before reaching a valid conclusion.",
            "example_from_trace": f"No run_end event or empty final answer (final_answer='{pred_ans}')"
        }
        summary_points.append("Premature termination")
    
    # ----- CATEGORY 2: Agent Output Errors -----
    
    # 2.1 Solver Failure
    solver_failed = False
    if not solver_ans:
        solver_failed = True
    else:
        # Check if solver output is too short (likely incomplete)
        solver_event = next(
            (e for e in trace if e.get("agent") == "solver" and e.get("event") == "completion_received"),
            None
        )
        if solver_event:
            content_head = solver_event.get("data", {}).get("content_head", "") or ""
            if len(content_head) < 30:
                solver_failed = True
    
    if solver_failed:
        failure_modes["2.1"] = {
            "name": "Solver Failure",
            "definition": "Solver doesn't produce a valid or complete answer.",
            "example_from_trace": f"Solver answer: '{solver_ans[:50]}' (length={len(solver_ans)})"
        }
        summary_points.append("Solver produced no/invalid answer")
    
    # 2.2 Checker Indecisiveness
    if verdict not in ("ACCEPT", "REJECT") and "checker" in agent_sequence:
        failure_modes["2.2"] = {
            "name": "Checker Indecisiveness",
            "definition": "Checker fails to give clear ACCEPT or REJECT verdict.",
            "example_from_trace": f"Verdict='{verdict}' (neither ACCEPT nor REJECT)"
        }
        summary_points.append("Checker indecisive")
    
    # 2.3 Refiner No-Op
    if refiner_ans and solver_ans:
        if normalize_answer(refiner_ans) == normalize_answer(solver_ans) and not success:
            failure_modes["2.3"] = {
                "name": "Refiner No-Op",
                "definition": "Refiner produces identical answer to solver without improvement.",
                "example_from_trace": f"Solver='{solver_ans[:30]}', Refiner='{refiner_ans[:30]}' (same)"
            }
            summary_points.append("Refiner made no changes")
    
    # 2.4 Arbiter Indecisiveness
    if "arbiter" in agent_sequence and (arbiter_pick == "" or arbiter_pick is None):
        failure_modes["2.4"] = {
            "name": "Arbiter Indecisiveness",
            "definition": "Arbiter fails to select a final answer from candidates.",
            "example_from_trace": "Arbiter decision field is empty or missing"
        }
        summary_points.append("Arbiter failed to choose")
    
    # ----- CATEGORY 3: Verification Errors -----
    
    # 3.1 Checker False Acceptance
    if verdict == "ACCEPT" and not success:
        failure_modes["3.1"] = {
            "name": "Checker False Acceptance",
            "definition": "Checker accepts an incorrect solution.",
            "example_from_trace": f"Verdict=ACCEPT but answer '{pred_ans[:30]}' is wrong (GT: {gt_ans})"
        }
        summary_points.append("False acceptance")
    
    # 3.2 Checker False Rejection
    if verdict == "REJECT" and success:
        failure_modes["3.2"] = {
            "name": "Checker False Rejection",
            "definition": "Checker rejects a correct solution.",
            "example_from_trace": f"Verdict=REJECT but final answer '{pred_ans[:30]}' is correct"
        }
        summary_points.append("False rejection")
    
    # ----- CATEGORY 4: Coordination Errors -----
    
    # Check if solver/refiner answers are correct
    solver_correct = answers_match(solver_ans, gt_ans) if solver_ans else False
    refiner_correct = answers_match(refiner_ans, gt_ans) if refiner_ans else False
    
    # 4.1 Refiner Degradation
    if refiner_ans and solver_ans:
        if normalize_answer(refiner_ans) != normalize_answer(solver_ans):
            # Refiner changed the answer
            if solver_correct and not refiner_correct:
                failure_modes["4.1"] = {
                    "name": "Refiner Degradation",
                    "definition": "Refiner changes a correct answer to an incorrect one.",
                    "example_from_trace": f"Solver='{solver_ans[:30]}' (correct) → Refiner='{refiner_ans[:30]}' (wrong)"
                }
                summary_points.append("Refiner made it worse")
            elif not success and refiner_ans:
                failure_modes["4.1"] = {
                    "name": "Refiner Degradation",
                    "definition": "Refiner fails to improve or worsens the answer.",
                    "example_from_trace": f"Solver='{solver_ans[:30]}', Refiner='{refiner_ans[:30]}', both wrong"
                }
                summary_points.append("Refiner didn't improve")
    
    # 4.2 Arbiter Poor Decision
    if "arbiter" in agent_sequence and not success:
        if solver_correct or refiner_correct:
            failure_modes["4.2"] = {
                "name": "Arbiter Poor Decision",
                "definition": "Arbiter chooses wrong candidate when a correct one exists.",
                "example_from_trace": (
                    f"Solver correct={solver_correct}, Refiner correct={refiner_correct}, "
                    f"but arbiter chose wrong answer"
                )
            }
            summary_points.append("Arbiter chose wrong candidate")
    
    # 4.3 Coordination Failure (Meta)
    # Multiple agents involved with multiple failure modes
    if num_agents >= 3 and len(failure_modes) >= 2 and not success:
        failure_modes["4.3"] = {
            "name": "Coordination Failure (Meta)",
            "definition": "Multiple agents involved with compounding failures across the pipeline.",
            "example_from_trace": f"{num_agents} agents executed, {len(failure_modes)} failure modes detected"
        }
        summary_points.append("Multiple coordination failures")
    
    # ----- CATEGORY 5: Answer Quality Errors -----
    
    # 5.1 Computational Error
    # If task failed but no other failure modes detected, likely a computational error
    if not success and not failure_modes:
        failure_modes["5.1"] = {
            "name": "Computational Error",
            "definition": "Correct approach but wrong calculation or subtle mathematical mistake.",
            "example_from_trace": f"Predicted '{pred_ans}', expected {gt_ans} - no orchestration issues detected"
        }
        summary_points.append("Computational/mathematical error")
    
    # Generate summary
    if summary_points:
        summary = "; ".join(summary_points)
    else:
        summary = "Success - no failure modes detected" if success else "Failed with unknown cause"
    
    return {
        "num_agents": num_agents,
        "agent_sequence": agent_sequence[:10],  # First 10 to avoid huge lists
        "failure_modes": failure_modes,
        "summary": summary
    }

# ---------- Main ----------
def main():
    print("="*80)
    print("MANUAL FAILURE MODE ANNOTATIONS")
    print("="*80)
    
    # Load data
    print("\n[1/4] Loading data...")
    dataset = load_json(DATASET_PATH)
    agent_eval = load_json(AGENT_EVAL_PATH)
    predictions = load_json(PREDICTIONS_PATH)
    
    print(f"  Dataset: {len(dataset)} problems")
    print(f"  Evaluation: {agent_eval['correct']}/{agent_eval['total']} correct ({agent_eval['accuracy']:.2%})")
    print(f"  Predictions: {len(predictions)} results")
    
    # Create lookups
    print("\n[2/4] Creating lookups...")
    dataset_lookup = {str(item["id"]): item for item in dataset}
    eval_lookup = {r["id"]: r for r in agent_eval["details"]}
    pred_lookup = {str(p["id"]): p for p in predictions}
    
    # Annotate each problem
    print("\n[3/4] Analyzing traces...")
    annotations = []
    
    for idx, (problem_id, eval_result) in enumerate(eval_lookup.items(), 1):
        problem = dataset_lookup.get(problem_id)
        pred = pred_lookup.get(problem_id)
        
        if not problem or not pred:
            print(f"  [{idx}/{len(eval_lookup)}] {problem_id} - SKIPPED (missing data)")
            continue
        
        # Load trace
        trace_file = pred.get("trace_file", "")
        if trace_file:
            trace = load_trace(trace_file)
        else:
            trace = []
        
        # Analyze
        analysis = analyze_trace_manually(
            problem_id,
            trace,
            eval_result["correct"],
            eval_result["predicted"],
            eval_result["ground_truth"],
            problem["question"]
        )
        
        # Create annotation record
        annotation = {
            "problem_id": problem_id,
            "task": problem["question"][:200] + "...",
            "trace_file": trace_file,
            "num_agents": analysis["num_agents"],
            "agent_sequence": analysis["agent_sequence"],
            "success": eval_result["correct"],
            "predicted_answer": eval_result["predicted"],
            "ground_truth": eval_result["ground_truth"],
            "identified_failure_modes": analysis["failure_modes"],
            "summary": analysis["summary"]
        }
        
        annotations.append(annotation)
        print(f"  [{idx}/{len(eval_lookup)}] {problem_id} - {analysis['summary'][:60]}")
    
    # Save
    print(f"\n[4/4] Saving annotations...")
    save_json(annotations, OUTPUT_PATH)
    
    # Summary statistics
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    print(f"Total annotated: {len(annotations)}")
    print(f"Success: {sum(1 for a in annotations if a['success'])}")
    print(f"Failure: {sum(1 for a in annotations if not a['success'])}")
    
    # Failure mode distribution
    from collections import Counter
    fm_counts = Counter()
    for ann in annotations:
        for fm_code in ann["identified_failure_modes"].keys():
            fm_counts[fm_code] += 1
    
    print(f"\nFailure Mode Distribution:")
    for fm_code, count in sorted(fm_counts.items()):
        fm_name = annotations[0]["identified_failure_modes"].get(fm_code, {}).get("name", fm_code)
        # Get actual name from first occurrence
        for ann in annotations:
            if fm_code in ann["identified_failure_modes"]:
                fm_name = ann["identified_failure_modes"][fm_code]["name"]
                break
        print(f"  {fm_code} {fm_name}: {count}")
    
    print(f"\n{'='*80}")

if __name__ == "__main__":
    main()
