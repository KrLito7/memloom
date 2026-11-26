"""Antigravity transcripts: recognised by path, parsed into turns, tools paired with results."""
import json
import os
import shutil
import unittest

from memloom.adapters import detect_adapter, get_adapter

from ._helpers import mktemp

CONV = "11111111-2222-3333-4444-555555555555"

ROWS = [
    {"step_index": 0, "source": "USER_EXPLICIT", "type": "USER_INPUT", "created_at": "2026-11-26T10:00:00Z",
     "content": "<USER_REQUEST>\n修一下 src/app.py 的报错\n</USER_REQUEST>\n<ADDITIONAL_METADATA>\nlocal time\n</ADDITIONAL_METADATA>"},
    {"step_index": 1, "source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": "2026-11-26T10:00:05Z",
     "model": "some-model", "content": "我先跑一下测试。",
     "tool_calls": [{"name": "run_command", "args": {"CommandLine": "\"python -m pytest\"", "toolSummary": "run tests"}}]},
    {"step_index": 2, "source": "MODEL", "type": "GENERIC", "created_at": "2026-11-26T10:00:08Z",
     "content": "ModuleNotFoundError: No module named 'requests'"},
    {"step_index": 3, "source": "SYSTEM", "type": "SYSTEM_MESSAGE", "created_at": "2026-11-26T10:00:09Z",
     "content": "Reminder: work efficiently."},
    {"step_index": 4, "source": "MODEL", "type": "PLANNER_RESPONSE", "created_at": "2026-11-26T10:00:20Z",
     "model": "some-model", "content": "装好依赖了。",
     "tool_calls": [{"name": "run_command", "args": {"CommandLine": "pip install requests"}}]},
    {"step_index": 5, "source": "MODEL", "type": "GENERIC", "created_at": "2026-11-26T10:00:30Z",
     "content": "Successfully installed requests"},
]


def _write(root, name="transcript.jsonl"):
    d = os.path.join(root, ".gemini", "antigravity", "brain", CONV, ".system_generated", "logs")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        for row in ROWS:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return p


class AntigravityTest(unittest.TestCase):
    def setUp(self):
        self.d = mktemp()
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)

    def test_transcript_is_claimed_but_the_full_copy_is_not(self):
        a = detect_adapter(_write(self.d))
        self.assertIsNotNone(a)
        self.assertEqual(a.name, "antigravity")
        self.assertIsNone(detect_adapter(_write(self.d, "transcript_full.jsonl")))

    def test_load_builds_turns_from_user_and_model_steps(self):
        s = get_adapter("antigravity").load(_write(self.d))
        self.assertEqual(s.id, CONV)
        self.assertEqual(s.model, "some-model")
        self.assertEqual(s.n_prompts, 1)
        self.assertEqual(s.turns[0].prompt, "修一下 src/app.py 的报错")  # wrapper + metadata stripped
        self.assertIn("装好依赖了", s.turns[0].reply)
        self.assertNotIn("Reminder", s.turns[0].reply)  # harness reminders are not conversation
        self.assertEqual(s.n_tools, 2)
        self.assertEqual(s.date, "2026-11-26")

    def test_tool_results_pair_in_order_and_failures_are_flagged(self):
        s = get_adapter("antigravity").load(_write(self.d))
        first, second = s.turns[0].tools
        self.assertEqual(first.summary, "python -m pytest")  # double JSON quoting removed
        self.assertFalse(first.ok)
        self.assertIn("ModuleNotFoundError", first.error)
        self.assertTrue(second.ok)
        self.assertEqual(second.error, "")

    def test_empty_transcript_gives_no_session(self):
        p = _write(self.d)
        open(p, "w").close()
        self.assertIsNone(get_adapter("antigravity").load(p))


if __name__ == "__main__":
    unittest.main()