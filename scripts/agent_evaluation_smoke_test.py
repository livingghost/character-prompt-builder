#!/usr/bin/env python3
"""Exercise runner mechanics with an explicit fixture process, not a real model."""

from pathlib import Path
import copy
import json
import sys
import tempfile
import unittest

import agent_evaluation as agent
import material_support as m
import repair_analysis as repair


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "prompt.txt").write_text("A constructed runner test. Not a model benchmark.\n")
        script = """import json, pathlib, sys
out=pathlib.Path(sys.argv[1]);(out/'result.txt').write_text('Fixture output, not generated prose.')
print(json.dumps({'event':'metrics','total_tokens':17,'tool_calls':2,'triggered':True,'completed':False}))
"""
        (self.root / "host.py").write_text(script)
        self.study = {
            "purpose": "Fixture only",
            "repetitions": 1,
            "cases": [
                {
                    "id": "case",
                    "prompt": "prompt.txt",
                    "inputs": ["host.py"],
                    "expected_outputs": ["result.txt"],
                    "criteria": ["Requires a human quality review."],
                }
            ],
            "conditions": [
                {
                    "id": "condition",
                    "host_label": "fixture process",
                    "model_label": "none (fixture)",
                    "argv": [sys.executable, "inputs/host.py", "{outputs}"],
                    "skill": None,
                    "timeout_seconds": 3,
                    "metrics": {
                        "match_pointer": "/event",
                        "match_value": "metrics",
                        "pointers": {
                            "total_tokens": "/total_tokens",
                            "tool_calls": "/tool_calls",
                            "triggered": "/triggered",
                            "completed": "/completed",
                        },
                    },
                }
            ],
        }
        self.save()

    def tearDown(self):
        self.tmp.cleanup()

    def save(self):
        (self.root / "study.json").write_bytes(m.encoded(self.study))

    def run_study(self):
        self.save()
        _, plan = agent.plan_study(self.root, "study.json", "evaluation")
        return agent.run_study(self.root, "study.json", "evaluation", plan["content_sha256"])

    def test_inspection_does_not_execute(self):
        _, plan = agent.plan_study(self.root, "study.json", "evaluation")
        self.assertFalse((self.root / "evaluation").exists())
        self.assertIsNotNone(plan["conditions"][0]["executable"])

    def test_explicit_plan_required(self):
        with self.assertRaisesRegex(ValueError, "approved"):
            agent.run_study(self.root, "study.json", "evaluation", "bad")

    def test_actual_process_logs_and_output_hashes(self):
        result = self.run_study()
        self.assertTrue(result["ok"])
        item = result["runs"][0]
        receipt = m.load(self.root, item["result"])
        self.assertEqual(receipt["returncode"], 0)
        self.assertEqual(receipt["measurements"]["total_tokens"], 17)
        self.assertGreater(receipt["measurements"]["elapsed_seconds"], 0)
        self.assertTrue(receipt["host_observations"]["triggered"])
        self.assertFalse(receipt["host_observations"]["completed"])
        self.assertEqual(receipt["quality_verdict"], "not-reviewed")
        metrics = m.load(self.root, item["measurements"])
        self.assertEqual(
            agent.verify_measurements(self.root, item["result"], metrics["values"])["status"],
            "executed",
        )

    def test_existing_evaluator_consumes_retained_runner_evidence(self):
        import evaluation_evidence

        result = self.run_study()
        row = result["runs"][0]
        measured = evaluation_evidence._measurements(self.root, row["measurements"])
        self.assertEqual(measured["values"]["total_tokens"], 17)
        self.assertEqual(measured["runner_evidence"]["quality_verdict"], "not-reviewed")
        receipt = m.load(self.root, row["result"])
        (self.root / receipt["logs"][0]["path"]).write_text("changed telemetry")
        with self.assertRaisesRegex(ValueError, "evidence changed"):
            evaluation_evidence._measurements(self.root, row["measurements"])

    def test_unknown_metrics_are_not_estimated(self):
        self.study["conditions"][0]["metrics"] = None
        result = self.run_study()
        receipt = m.load(self.root, result["runs"][0]["result"])
        self.assertIsNone(receipt["measurements"]["total_tokens"])
        self.assertIsNone(receipt["host_observations"]["triggered"])

    def test_unavailable_host_is_retained(self):
        self.study["conditions"][0]["argv"] = ["no-such-evaluation-host-8ec8215"]
        result = self.run_study()
        self.assertFalse(result["ok"])
        receipt = m.load(self.root, result["runs"][0]["result"])
        self.assertEqual(receipt["status"], "unavailable")
        self.assertIsNone(receipt["measurements"]["elapsed_seconds"])

    def test_timeout_is_not_silently_retried(self):
        (self.root / "host.py").write_text("import time; time.sleep(20)")
        self.study["conditions"][0]["timeout_seconds"] = 0.15
        result = self.run_study()
        self.assertEqual(len(result["runs"]), 1)
        self.assertEqual(result["runs"][0]["status"], "timeout")

    def test_failed_process_is_retained(self):
        (self.root / "host.py").write_text("raise SystemExit(7)")
        result = self.run_study()
        receipt = m.load(self.root, result["runs"][0]["result"])
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["returncode"], 7)

    def test_repeated_trials_have_separate_workspaces(self):
        self.study["repetitions"] = 2
        result = self.run_study()
        self.assertEqual(len(result["runs"]), 2)
        a = m.load(self.root, result["runs"][0]["result"])
        b = m.load(self.root, result["runs"][1]["result"])
        self.assertNotEqual(a["outputs"][0]["path"], b["outputs"][0]["path"])

    def test_input_change_after_approval_refused(self):
        _, plan = agent.plan_study(self.root, "study.json", "evaluation")
        (self.root / "prompt.txt").write_text("changed")
        with self.assertRaisesRegex(ValueError, "approved"):
            agent.run_study(self.root, "study.json", "evaluation", plan["content_sha256"])

    def test_log_tampering_detected(self):
        result = self.run_study()
        row = result["runs"][0]
        receipt = m.load(self.root, row["result"])
        (self.root / receipt["logs"][0]["path"]).write_text("modified")
        with self.assertRaisesRegex(ValueError, "evidence changed"):
            agent.verify_measurements(self.root, row["result"], receipt["measurements"])

    def test_metric_types_not_coerced(self):
        selector = self.study["conditions"][0]["metrics"]
        values, seen = agent.extract_metrics(
            b'{"event":"metrics","total_tokens":"17","tool_calls":true}\n', selector
        )
        self.assertEqual(values, {"total_tokens": None, "tool_calls": None})
        self.assertEqual(len(seen["invalid_metrics"]), 2)

    def test_small_skill_copy_is_self_contained(self):
        skill = self.root / "input-skill"
        skill.mkdir()
        (skill / "SKILL.md").write_text("Fixture skill only.")
        self.study["conditions"][0]["skill"] = "input-skill"
        result = self.run_study()
        directory = (self.root / result["runs"][0]["result"]).parent
        self.assertEqual((directory / "skill/SKILL.md").read_text(), "Fixture skill only.")

    def test_missing_expected_output_is_not_a_successful_study(self):
        (self.root / "host.py").write_text('print("fixture completed without its deliverable")')
        result = self.run_study()
        self.assertFalse(result["ok"])
        receipt = m.load(self.root, result["runs"][0]["result"])
        self.assertEqual(receipt["returncode"], 0)
        self.assertEqual(receipt["missing_outputs"], ["result.txt"])
        self.assertEqual(receipt["quality_verdict"], "not-reviewed")

    def test_fast_log_overflow_is_not_successful_evidence(self):
        from unittest.mock import patch

        (self.root / "host.py").write_text(
            "import pathlib, sys\n"
            'pathlib.Path(sys.argv[1], "result.txt").write_text("Fixture output")\n'
            'sys.stdout.buffer.write(b"x" * 4096 + b"\\n")\n'
        )
        self.study["conditions"][0]["max_log_bytes"] = 64
        original_popen = agent.subprocess.Popen

        def already_finished(*args, **kwargs):
            process = original_popen(*args, **kwargs)
            process.wait(timeout=5)
            return process

        with (
            patch.object(agent.subprocess, "Popen", side_effect=already_finished),
        ):
            result = self.run_study()
        self.assertFalse(result["ok"])
        receipt = m.load(self.root, result["runs"][0]["result"])
        self.assertEqual(receipt["status"], "log-limit")
        self.assertFalse(any(log["truncated"] for log in receipt["logs"]))
        self.assertTrue(any(log["operator_budget_exceeded"] for log in receipt["logs"]))
        self.assertEqual((self.root / receipt["logs"][0]["path"]).read_bytes(), b"x"*4096+b"\n")
        self.assertIsNone(receipt["measurements"]["total_tokens"])

    def test_prompt_is_read_from_the_verified_copy(self):
        from unittest.mock import patch

        _, plan = agent.plan_study(self.root, "study.json", "evaluation")
        base = self.root / "evaluation"
        base.mkdir()
        expected_prompt = (self.root / "prompt.txt").read_text()
        original_write = agent._write

        def change_original_after_copy(path, raw):
            original_write(path, raw)
            if path.name == "prompt.txt" and path.parent.name == "inputs":
                (self.root / "prompt.txt").write_text("Changed after the verified copy was saved.")

        with patch.object(agent, "_write", side_effect=change_original_after_copy):
            row = agent.execute_trial(
                self.root,
                base,
                self.study["cases"][0],
                self.study["conditions"][0],
                plan["conditions"][0],
                plan["cases"][0],
                1,
                plan["content_sha256"],
            )
        retained_prompt = (self.root / row["result"]).parent / "prompt.txt"
        self.assertEqual(retained_prompt.read_text(), expected_prompt)


class FailureTests(unittest.TestCase):
    def rendered_analysis(self, report, hypotheses=None):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            hypotheses_path = None
            if hypotheses is not None:
                hypotheses_path = "hypotheses.json"
                (root / hypotheses_path).write_bytes(m.encoded({"hypotheses": hypotheses}))
            with patch.object(repair.artifact_review, "build", return_value=(report, None)):
                repair.analyze(root, [report["run"]], "analysis", hypotheses_path)
            return (root / "analysis/analysis.md").read_text()

    def report(self, run="run", text="Preserve the declared condition."):
        return {
            "run": run,
            "input_sha256": "a" * 64,
            "receipt_head": "b" * 64,
            "current": True,
            "changed_dependencies": [],
            "criteria": [{"id": "c", "text": text, "strength": "hard"}],
            "candidates": [
                {
                    "id": "candidate",
                    "reviews": [
                        {
                            "receipt": "r",
                            "review": {
                                "observations": [{"observation": "Recorded failure."}],
                                "checks": [
                                    {
                                        "criterion": "c",
                                        "verdict": "fail",
                                        "observation_indices": [0],
                                        "reason": "Observed mismatch.",
                                    }
                                ],
                            },
                        }
                    ],
                }
            ],
        }

    def test_groups_by_actual_requirement_not_local_id(self):
        result = repair.summarize([self.report("a"), self.report("b", "A different requirement.")])
        self.assertEqual(len(result["failure_groups"]), 2)

    def test_repetition_does_not_authorize_retry(self):
        result = repair.summarize([self.report("a"), self.report("b")])
        self.assertEqual(result["failure_groups"][0]["run_count"], 2)
        self.assertFalse(result["execution_authorized"])
        self.assertFalse(result["canon_changed"])
        self.assertEqual(result["hypotheses"], [])

    def test_duplicate_run_is_not_an_independent_attempt(self):
        with self.assertRaises(ValueError):
            repair.summarize([self.report(), self.report()])

    def test_unsupported_cause_cannot_name_missing_evidence(self):
        h = {
            "hypothesis_id": "h",
            "group_ids": ["absent"],
            "explanation": "A hypothesis.",
            "alternatives": [],
            "proposed_change": "A proposal.",
            "protected_requirements": [],
            "acceptance_check": "Inspect actual output.",
            "scope": "Only this work.",
        }
        with self.assertRaisesRegex(ValueError, "not linked"):
            repair.summarize([self.report()], [h])

    def test_readable_analysis_retains_observations_and_locators(self):
        report = self.report()
        observation = report["candidates"][0]["reviews"][0]["review"]["observations"][0]
        observation["location"] = {"file": "result.txt", "lines": [4, 6]}
        report["current"] = False
        report["changed_dependencies"] = [{"path": "persona.txt", "reason": "source changed"}]
        result = repair.summarize([report])
        text = self.rendered_analysis(report)
        self.assertIn("Recorded failure.", text)
        self.assertIn("result.txt", text)
        self.assertIn("persona.txt", text)
        self.assertIn("source changed", text)
        self.assertIn(result["failure_groups"][0]["group_id"], text)
        self.assertIn(report["input_sha256"], text)

    def test_readable_hypothesis_keeps_evidence_link_and_protected_requirements(self):
        report = self.report()
        group_id = repair.summarize([report])["failure_groups"][0]["group_id"]
        hypothesis = {
            "hypothesis_id": "hypothesis",
            "group_ids": [group_id],
            "explanation": "Possible cause, not established.",
            "alternatives": ["A different cause is still possible."],
            "proposed_change": "Change only the declared response.",
            "protected_requirements": ["Retain the partner-specific exception."],
            "acceptance_check": "Inspect the cited output passage.",
            "scope": "Only the selected scene.",
        }
        text = self.rendered_analysis(report, [hypothesis])
        for field in ("explanation", "proposed_change", "acceptance_check", "scope"):
            self.assertIn(hypothesis[field], text)
        self.assertIn(group_id, text)
        self.assertIn(hypothesis["protected_requirements"][0], text)
        self.assertIn(hypothesis["alternatives"][0], text)
        self.assertIn("hypothesis-not-established", text)


if __name__ == "__main__":
    unittest.main()
