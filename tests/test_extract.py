"""Pure-stdlib extraction: what becomes a path, a command, a pitfall."""
import unittest

from memloom.extract import (
    error_lines,
    extract_commands,
    extract_paths,
    fingerprint,
    is_error_line,
    path_component,
    signature_key,
)


class ErrorLineTest(unittest.TestCase):
    def test_real_failures_are_kept(self):
        for line in (
            "Error: cannot read path/to/app.ts — not found",
            "TypeError: x is not a function",
            "TRANSPORT ERROR: Error: connect ECONNREFUSED 127.0.0.1:63439",
            "FAIL src/app.test.ts",
            "AttributeError: 'NoneType' object has no attribute 'load'",
            "error: 拉评论失败",
            "Traceback (most recent call last):",
            "zstd: no such file",
            "exit code: 2",
        ):
            self.assertTrue(is_error_line(line), line)

    def test_instructions_about_failure_are_not_failures(self):
        # Real example from a duty prompt: prose that merely mentions「失败」. Grouping it
        # as a repeated bug put a 40-session false topic in the 踩坑 folder.
        prose = (
            "⭐ 保底：不管发生什么，报告至少留一行（哪怕只写「本轮失败：原因是 X」），别让 out/ 空着。"
        )
        self.assertFalse(is_error_line(prose))
        self.assertFalse(is_error_line("（写代码、报错、讲技术细节时照常写，「程序」只在指代码本身时用。）"))
        self.assertFalse(is_error_line("如果要失败，请在报告里写清楚失败，并且说明原因和下一步"))
        self.assertFalse(is_error_line("short"))
        self.assertFalse(is_error_line(""))

    def test_error_lines_are_deduped_by_fingerprint(self):
        lines = [
            "Error: cannot read C:/work/a.ts — not found",
            "Error: cannot read D:/proj/b.ts — not found",
            "all good here",
        ]
        fps = {fingerprint(x) for x in lines if is_error_line(x)}
        self.assertEqual(len(fps), 1)
        self.assertIn("<path>", fps.pop())


class FingerprintTest(unittest.TestCase):
    def test_volatile_parts_collapse(self):
        a = fingerprint("Error: 6a1d5b8e-1111-2222-3333-444455556666 at 2026-11-13T14:38:35 code 42")
        b = fingerprint("Error: 9f9f9f9f-9999-8888-7777-666655554444 at 2025-01-02T03:04:05 code 7")
        self.assertEqual(a, b)

    def test_trailing_punctuation_goes(self):
        self.assertEqual(fingerprint("error: 拉评论失败,"), fingerprint("error: 拉评论失败"))
        self.assertFalse(fingerprint("Error: {").endswith("{"))


class PathsTest(unittest.TestCase):
    def test_urls_are_not_paths(self):
        paths = extract_paths(["see http://example.com/v1/search and C:/work/app.ts"])
        self.assertIn("C:/work/app.ts", paths)
        self.assertFalse([p for p in paths if "example.com" in p])

    def test_child_path_shadows_parent(self):
        paths = extract_paths(["edit C:/work/app/src/main.ts"])
        self.assertIn("C:/work/app/src/main.ts", paths)
        self.assertNotIn("C:/work/app/src", paths)

    def test_path_component_picks_the_meaningful_part(self):
        self.assertTrue(path_component("C:/work/app/src/main.ts"))


class CommandsTest(unittest.TestCase):
    def test_known_command_heads(self):
        cmds = extract_commands(["$ pytest -q tests", "npm run build"])
        self.assertIn("pytest", cmds)
        self.assertIn("npm", cmds)


class SignatureTest(unittest.TestCase):
    def test_signature_is_short_and_stable(self):
        a = signature_key("Error: boom")
        self.assertEqual(a, signature_key("Error: boom"))
        self.assertEqual(len(a), 10)
        self.assertNotEqual(a, signature_key("Error: bang"))


if __name__ == "__main__":
    unittest.main()


class NoiseFilterTests(unittest.TestCase):
    def test_user_decisions_and_bare_codes_are_not_bugs(self):
        from memloom.extract import is_error_line
        for line in ("the user cancelled", "The user rejected tool use",
                     "+ CategoryInfo : ParserError"):
            self.assertFalse(is_error_line(line), line)

    def test_real_errors_still_count(self):
        from memloom.extract import is_error_line
        for line in ("ModuleNotFoundError: No module named 'x'", "fatal: not a git repository",
                     "connect ECONNREFUSED 127.0.0.1:8080"):
            self.assertTrue(is_error_line(line), line)

    def test_random_job_ids_and_plumbing_are_not_code_topics(self):
        from memloom.group import _is_code_topic
        for name in ("tasks／b08k6i984", "AppData／Local", "chrome-profile／Default",
                     "Program Files"):
            self.assertFalse(_is_code_topic(name), name)
        self.assertTrue(_is_code_topic("dafeiyu／film"))


class LowInformationTests(unittest.TestCase):
    def test_symptomless_fingerprints_are_dropped(self):
        from memloom.group import _low_information
        for fp in ("Traceback", "Exit code N", "Exit code <n>", "pg.on", '<n> pg.on("console", lambda m: m.type)'):
            self.assertTrue(_low_information(fp), fp)
        for fp in ("SyntaxError", "ECONNREFUSED", "No such file or directory"):
            self.assertFalse(_low_information(fp), fp)
