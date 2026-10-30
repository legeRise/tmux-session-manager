#!/usr/bin/env python3
"""Integration tests for tmux-manager.

Each test runs its own tmux server in a private TMUX_TMPDIR and its own
TMUX_MANAGER_HOME, so the user's sessions and saved workspaces are never
touched.

Run with:
    python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tmux-manager"
TMUX = shutil.which("tmux")


@unittest.skipUnless(TMUX, "tmux is required for the integration tests")
class TmuxManagerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="tmux-manager-test-"))
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.tmux_dir = self.tmp / "tmux"
        self.tmux_dir.mkdir()
        self.data = self.tmp / "data"
        self.proj = self.tmp / "proj"
        self.proj.mkdir()
        self.other = self.tmp / "other"
        self.other.mkdir()

        self.env = os.environ.copy()
        self.env.update(
            {
                "HOME": str(self.home),
                "TMUX_TMPDIR": str(self.tmux_dir),
                "TMUX_MANAGER_HOME": str(self.data),
                "SHELL": "/bin/bash",
                "TERM": "xterm-256color",
            }
        )
        self.env.pop("TMUX", None)
        self.env.pop("TMUX_PANE", None)
        self.env.pop("XDG_DATA_HOME", None)

        # Make the panes use bash regardless of the login shell, so the
        # POSIX commands used by these tests behave the same everywhere.
        bash = shutil.which("bash")
        if bash:
            self.run_tmux(
                "new-session", "-d", "-s", "__tmux_manager_test__"
            )
            self.run_tmux("set-option", "-g", "default-shell", bash)

    def tearDown(self) -> None:
        self.run_tmux("kill-server", check=False)
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ------------------------------------------------------------------ tools

    def run_tool(
        self,
        *args: str,
        input_text: str | None = None,
        env_extra: dict[str, str] | None = None,
        check: bool = False,
    ) -> subprocess.CompletedProcess:
        env = self.env.copy()
        if env_extra:
            env.update(env_extra)
        result = subprocess.run(
            [sys.executable, str(TOOL), *args],
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            input=input_text,
        )
        if check and result.returncode != 0:
            self.fail(
                f"tmux-manager {' '.join(args)} failed with "
                f"{result.returncode}\nstdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )
        return result

    def run_tmux(
        self, *args: str, check: bool = True
    ) -> subprocess.CompletedProcess:
        result = subprocess.run(
            ["tmux", *args],
            env=self.env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if check and result.returncode != 0:
            self.fail(
                f"tmux {' '.join(args)} failed with {result.returncode}: "
                f"{result.stderr}"
            )
        return result

    def tmux_out(self, *args: str) -> str:
        return self.run_tmux(*args).stdout.rstrip("\n")

    def tmux_lines(self, *args: str) -> list[str]:
        output = self.tmux_out(*args)
        return [line for line in output.splitlines() if line]

    def pane_map(self, session: str) -> dict[tuple[int, int], str]:
        lines = self.tmux_lines(
            "list-panes",
            "-s",
            "-t",
            session,
            "-F",
            "#{window_index}:#{pane_index} #{pane_id}",
        )
        mapping: dict[tuple[int, int], str] = {}
        for line in lines:
            target, pane_id = line.split()
            window, pane = target.split(":")
            mapping[(int(window), int(pane))] = pane_id
        return mapping

    def pane_option(self, pane_id: str, option: str) -> str:
        result = self.run_tmux(
            "show-options", "-p", "-t", pane_id, "-v", option, check=False
        )
        if result.returncode != 0:
            return ""
        return result.stdout.strip()

    def workspace_file(self, name: str) -> Path:
        return self.data / "workspaces" / f"{name}.yaml"

    def load_workspace(self, name: str) -> dict:
        with self.workspace_file(name).open(encoding="utf-8") as handle:
            return yaml.safe_load(handle)

    def wait_for_file(self, path: Path, timeout: float = 8.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if path.exists():
                return True
            time.sleep(0.05)
        return False

    # ------------------------------------------------------------------ setups

    def make_source(self, session: str = "src") -> dict:
        """Three windows (indexes 0, 3, 5), duplicate names, commands,
        pane titles, an active pane per window, a gap, and a zoomed window."""
        out = self.tmp / "roundtrip-out.txt"
        marker = self.tmp / "roundtrip-marker.txt"

        self.run_tmux(
            "new-session",
            "-d",
            "-s",
            session,
            "-n",
            "code",
            "-c",
            str(self.proj),
        )
        self.run_tmux(
            "split-window", "-t", f"{session}:0", "-c", str(self.other)
        )
        self.run_tmux(
            "new-window",
            "-t",
            f"{session}:3",
            "-n",
            "PSR Website:",
            "-c",
            str(self.proj),
        )
        self.run_tmux(
            "split-window", "-t", f"{session}:3", "-c", str(self.proj)
        )
        self.run_tmux(
            "new-window",
            "-t",
            f"{session}:5",
            "-n",
            "code",
            "-c",
            str(self.proj),
        )

        panes = self.pane_map(session)
        self.run_tmux(
            "set",
            "-p",
            "-t",
            panes[(0, 0)],
            "@tm_command",
            f'VAR=1 printf "%s\\n" "a b" > {out}',
        )
        self.run_tmux(
            "set",
            "-p",
            "-t",
            panes[(5, 0)],
            "@tm_command",
            f"printf 'ran\\n' > {marker}",
        )
        self.run_tmux(
            "select-pane", "-t", panes[(0, 1)], "-T", "my pane title"
        )
        self.run_tmux(
            "select-pane", "-t", panes[(3, 1)], "-T", "second title"
        )

        # Window 0 keeps pane 1 active, window 3 is active and zoomed on pane 0.
        self.run_tmux("select-pane", "-t", panes[(0, 1)])
        self.run_tmux("select-window", "-t", f"{session}:3")
        self.run_tmux("select-pane", "-t", panes[(3, 0)])
        self.run_tmux("resize-pane", "-Z", "-t", panes[(3, 0)])

        return {
            "out": out,
            "marker": marker,
            "panes": panes,
        }

    # ------------------------------------------------------------------- tests

    def test_export_restore_round_trip(self) -> None:
        source = self.make_source()
        geometry = self.tmux_lines(
            "list-panes",
            "-t",
            "src:0",
            "-F",
            "#{pane_left},#{pane_top},#{pane_width},#{pane_height}",
        )

        self.run_tool("export", "-t", "src", "-n", "demo", check=True)
        data = self.load_workspace("demo")

        self.assertEqual(
            [window["index"] for window in data["windows"]], [0, 3, 5]
        )
        self.assertEqual(
            [window["name"] for window in data["windows"]],
            ["code", "PSR Website:", "code"],
        )
        self.assertEqual(data["active_window"], 3)

        window0, window3, window5 = data["windows"]
        self.assertEqual(window0["active_pane"], 1)
        self.assertTrue(window3["zoomed"])
        self.assertEqual(window0["panes"][0]["command"],
                         f'VAR=1 printf "%s\\n" "a b" > {source["out"]}')
        self.assertEqual(window0["panes"][1]["title"], "my pane title")
        self.assertEqual(window3["panes"][1]["title"], "second title")
        self.assertNotIn("guessed", window0["panes"][0])

        self.run_tool(
            "restore", "demo", "--as", "restored", "--yes", check=True
        )

        windows = self.tmux_lines(
            "list-windows",
            "-t",
            "restored",
            "-F",
            "#{window_index}\t#{window_name}\t#{window_active}\t#{window_zoomed_flag}",
        )
        self.assertEqual(
            windows,
            [
                "0\tcode\t0\t0",
                "3\tPSR Website:\t1\t1",
                "5\tcode\t0\t0",
            ],
        )

        pane_rows = self.tmux_lines(
            "list-panes",
            "-s",
            "-t",
            "restored",
            "-F",
            "#{window_index}:#{pane_index}\t#{pane_current_path}\t"
            "#{pane_active}\t#{pane_title}",
        )
        rows = {}
        for line in pane_rows:
            target, cwd, active, title = line.split("\t")
            rows[target] = (cwd, active, title)

        self.assertEqual(rows["0:0"][0], str(self.proj))
        self.assertEqual(rows["0:1"][0], str(self.other))
        self.assertEqual(rows["0:1"][1], "1")
        self.assertEqual(rows["0:1"][2], "my pane title")
        self.assertEqual(rows["3:0"][0], str(self.proj))
        self.assertEqual(rows["3:0"][1], "1")
        self.assertEqual(rows["3:1"][2], "second title")
        self.assertEqual(rows["5:0"][0], str(self.proj))
        self.assertEqual(rows["5:0"][1], "1")

        restored_geometry = self.tmux_lines(
            "list-panes",
            "-t",
            "restored:0",
            "-F",
            "#{pane_left},#{pane_top},#{pane_width},#{pane_height}",
        )
        self.assertEqual(geometry, restored_geometry)

        self.assertTrue(
            self.wait_for_file(source["out"]),
            "the restored command did not run",
        )
        self.assertEqual(source["out"].read_text(), "a b\n")
        self.assertTrue(self.wait_for_file(source["marker"]))
        self.assertEqual(source["marker"].read_text(), "ran\n")

    @unittest.skipUnless(
        shutil.which("pgrep") and shutil.which("ps"),
        "pgrep and ps are needed for command guessing",
    )
    def test_export_guessed_command(self) -> None:
        self.run_tmux(
            "new-session", "-d", "-s", "guess", "-n", "g", "-c", str(self.proj)
        )
        self.run_tmux("send-keys", "-t", "guess:0", "sleep 60", "Enter")
        deadline = time.monotonic() + 5
        current = ""
        while time.monotonic() < deadline:
            current = self.tmux_out(
                "display-message",
                "-p",
                "-t",
                "guess:0",
                "#{pane_current_command}",
            )
            if current == "sleep":
                break
            time.sleep(0.1)
        self.assertEqual(current, "sleep")

        self.run_tool("export", "-t", "guess", "-n", "guess", check=True)
        data = self.load_workspace("guess")
        pane = data["windows"][0]["panes"][0]
        self.assertEqual(pane["command"], "sleep 60")
        self.assertTrue(pane["guessed"])

    def test_shell_hook_records_exact_command(self) -> None:
        bash = shutil.which("bash")
        if not bash:
            self.skipTest("bash is required for the hook test")

        # Prompt commands must not be mistaken for user input.
        (self.home / ".bashrc").write_text(
            "PROMPT_COMMAND='echo prompt-command >/dev/null'\n",
            encoding="utf-8",
        )
        self.run_tool("install-hook", check=True)
        self.run_tmux("set-option", "-g", "default-command", f"{bash} -i")
        self.run_tmux(
            "new-session", "-d", "-s", "hooked", "-n", "one",
            "-c", str(self.proj),
        )
        time.sleep(0.4)
        pane = self.pane_map("hooked")[(0, 0)]
        exact = 'VAR=1 sleep 30 # keep "a b" here'

        self.run_tmux("send-keys", "-t", pane, exact, "Enter")
        deadline = time.monotonic() + 5
        recorded = ""
        while time.monotonic() < deadline:
            recorded = self.pane_option(pane, "@tm_command")
            if recorded:
                break
            time.sleep(0.05)
        self.assertEqual(recorded, exact)

        self.run_tmux("send-keys", "-t", pane, "C-c")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            recorded = self.pane_option(pane, "@tm_command")
            if not recorded:
                break
            time.sleep(0.05)
        self.assertEqual(recorded, "")

        # A background job must not survive as the pane command.
        self.run_tmux("send-keys", "-t", pane, "sleep 5 &", "Enter")
        time.sleep(0.4)
        self.assertEqual(self.pane_option(pane, "@tm_command"), "")

        self.run_tmux("send-keys", "-t", pane, exact, "Enter")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            recorded = self.pane_option(pane, "@tm_command")
            if recorded:
                break
            time.sleep(0.05)
        self.assertEqual(recorded, exact)

        self.run_tool("export", "-t", "hooked", "-n", "hooked", check=True)
        data = self.load_workspace("hooked")
        saved = data["windows"][0]["panes"][0]
        self.assertEqual(saved["command"], exact)
        self.assertNotIn("guessed", saved)

    def test_export_no_commands(self) -> None:
        self.make_source()
        self.run_tool(
            "export", "-t", "src", "-n", "nocom", "--no-commands", check=True
        )
        data = self.load_workspace("nocom")
        for window in data["windows"]:
            for pane in window["panes"]:
                self.assertEqual(pane["command"], "")
                self.assertNotIn("guessed", pane)
        self.assertEqual([w["index"] for w in data["windows"]], [0, 3, 5])

    def test_restore_no_commands(self) -> None:
        source = self.make_source()
        self.run_tool("export", "-t", "src", "-n", "demo", check=True)
        self.run_tool(
            "restore",
            "demo",
            "--as",
            "quiet",
            "--yes",
            "--no-commands",
            check=True,
        )

        # Give a wrongly sent command enough time to create its marker.
        time.sleep(1.0)
        self.assertFalse(source["out"].exists())
        self.assertFalse(source["marker"].exists())
        windows = self.tmux_lines(
            "list-windows", "-t", "quiet", "-F", "#{window_index}"
        )
        self.assertEqual(windows, ["0", "3", "5"])

    def test_missing_folder_skips_command(self) -> None:
        gone = self.tmp / "gone"
        gone.mkdir()
        marker = self.tmp / "must-not-exist.txt"

        self.run_tmux(
            "new-session", "-d", "-s", "miss", "-n", "code", "-c", str(self.proj)
        )
        self.run_tmux("split-window", "-t", "miss:0", "-c", str(gone))
        panes = self.pane_map("miss")
        self.run_tmux(
            "set",
            "-p",
            "-t",
            panes[(0, 1)],
            "@tm_command",
            f"printf 'ran\\n' > {marker}",
        )

        self.run_tool("export", "-t", "miss", "-n", "missing", check=True)
        gone.rmdir()
        result = self.run_tool(
            "restore", "missing", "--as", "missing-restored", "--yes"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        time.sleep(1.0)

        self.assertFalse(marker.exists(), "command ran in a missing folder")
        restored = self.pane_map("missing-restored")
        cwd = self.tmux_out(
            "display-message",
            "-p",
            "-t",
            restored[(0, 1)],
            "#{pane_current_path}",
        )
        self.assertEqual(cwd, str(self.home))
        self.assertIn("window 'code' (index 0), pane 1", result.stderr)
        self.assertIn(str(gone), result.stderr)
        self.assertIn("does not exist", result.stderr)

    def test_if_missing(self) -> None:
        self.make_source()
        self.run_tool("export", "-t", "src", "-n", "bootme", check=True)
        log = self.tmp / "restore.log"

        self.run_tool(
            "restore",
            "bootme",
            "--if-missing",
            "--yes",
            "--log",
            str(log),
            check=True,
        )
        self.assertIn("Restore complete", log.read_text(encoding="utf-8"))
        first_panes = self.tmux_lines(
            "list-panes", "-s", "-t", "bootme", "-F", "#{pane_id}"
        )
        self.assertEqual(len(first_panes), 5)

        second = self.run_tool(
            "restore",
            "bootme",
            "--if-missing",
            "--yes",
            "--log",
            str(log),
            check=True,
        )
        self.assertIn("nothing to do", second.stdout)
        self.assertIn("nothing to do", log.read_text(encoding="utf-8"))
        second_panes = self.tmux_lines(
            "list-panes", "-s", "-t", "bootme", "-F", "#{pane_id}"
        )
        self.assertEqual(first_panes, second_panes)

    def test_first_window_keeps_nonzero_index(self) -> None:
        self.run_tmux(
            "new-session", "-d", "-s", "odd", "-n", "one", "-c", str(self.proj)
        )
        self.run_tmux("move-window", "-s", "odd:0", "-t", "odd:4")

        self.run_tool("export", "-t", "odd", "-n", "odd", check=True)
        data = self.load_workspace("odd")
        self.assertEqual([w["index"] for w in data["windows"]], [4])

        self.run_tool(
            "restore", "odd", "--as", "odd-restored", "--yes", check=True
        )
        windows = self.tmux_lines(
            "list-windows", "-t", "odd-restored", "-F", "#{window_index}"
        )
        self.assertEqual(windows, ["4"])

    def test_old_yaml_format_restores(self) -> None:
        workspaces = self.data / "workspaces"
        workspaces.mkdir(parents=True)
        old = {
            "workspace": "oldstyle",
            "source_session": "oldstyle",
            "windows": [
                {
                    "name": "legacy",
                    "index": 3,
                    "layout": "",
                    "panes": [
                        {
                            "index": 0,
                            "cwd": str(self.proj),
                            "command": "sleep 60",
                        }
                    ],
                }
            ],
        }
        (workspaces / "oldstyle.yaml").write_text(
            yaml.safe_dump(old, sort_keys=False), encoding="utf-8"
        )

        self.run_tool(
            "restore", "oldstyle", "--as", "old-restored", "--yes", check=True
        )
        windows = self.tmux_lines(
            "list-windows",
            "-t",
            "old-restored",
            "-F",
            "#{window_index}\t#{window_name}",
        )
        self.assertEqual(windows, ["3\tlegacy"])
        panes = self.tmux_lines(
            "list-panes",
            "-t",
            "old-restored:3",
            "-F",
            "#{pane_current_path}",
        )
        self.assertEqual(panes, [str(self.proj)])

    def test_delay_and_wait_for_file(self) -> None:
        out = self.tmp / "waited-command.txt"
        ready = self.tmp / "dependency.ready"
        self.run_tmux(
            "new-session", "-d", "-s", "wait", "-n", "api", "-c", str(self.proj)
        )
        pane = self.pane_map("wait")[(0, 0)]
        self.run_tmux(
            "set",
            "-p",
            "-t",
            pane,
            "@tm_command",
            f"printf 'ok\\n' > {out}",
        )
        self.run_tool("export", "-t", "wait", "-n", "wait", check=True)

        data = self.load_workspace("wait")
        saved_pane = data["windows"][0]["panes"][0]
        saved_pane["delay"] = 0.3
        saved_pane["wait_for"] = str(ready)
        saved_pane["wait_timeout"] = 5
        (self.data / "workspaces" / "wait.yaml").write_text(
            yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
        )

        timer = threading.Timer(0.8, ready.touch)
        timer.start()
        started = time.monotonic()
        try:
            self.run_tool(
                "restore", "wait", "--as", "waited", "--yes", check=True
            )
        finally:
            timer.cancel()
        elapsed = time.monotonic() - started

        self.assertGreaterEqual(elapsed, 0.7)
        self.assertTrue(ready.exists())
        self.assertTrue(self.wait_for_file(out))
        self.assertEqual(out.read_text(encoding="utf-8"), "ok\n")

    def test_missing_windows(self) -> None:
        self.make_source()
        self.run_tool("export", "-t", "src", "-n", "demo", check=True)

        self.run_tmux(
            "new-session", "-d", "-s", "demo", "-n", "live", "-c", str(self.proj)
        )
        live_pane = self.pane_map("demo")[(0, 0)]
        self.run_tmux(
            "set", "-p", "-t", live_pane, "@tm_command", "echo live"
        )
        active_before = self.tmux_out(
            "display-message", "-p", "-t", "demo", "#{window_index}"
        )

        result = self.run_tool(
            "restore",
            "demo",
            "--missing-windows",
            "--yes",
            "--no-commands",
            check=True,
        )
        self.assertIn("Adding 2 missing window", result.stdout)

        windows = self.tmux_lines(
            "list-windows",
            "-t",
            "demo",
            "-F",
            "#{window_index}\t#{window_name}",
        )
        self.assertEqual(windows, ["0\tlive", "3\tPSR Website:", "5\tcode"])
        self.assertEqual(self.pane_map("demo")[(0, 0)], live_pane)

        live_command = self.pane_option(live_pane, "@tm_command")
        self.assertEqual(live_command, "echo live")
        self.assertEqual(
            self.tmux_out(
                "display-message", "-p", "-t", "demo", "#{window_index}"
            ),
            active_before,
        )

        again = self.run_tool(
            "restore", "demo", "--missing-windows", "--yes", check=True
        )
        self.assertIn("No missing windows", again.stdout)

    def test_snapshot_guard(self) -> None:
        self.make_source()
        self.run_tool("export", "-t", "src", "-n", "guard", check=True)
        before = self.workspace_file("guard").read_bytes()

        self.run_tmux("kill-window", "-t", "src:5")
        self.run_tmux("kill-window", "-t", "src:3")

        refused = self.run_tool(
            "export", "-t", "src", "-n", "guard", "--yes"
        )
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("fewer windows", refused.stderr)
        self.assertIn("refusing", refused.stderr.lower())
        self.assertEqual(self.workspace_file("guard").read_bytes(), before)

        forced = self.run_tool(
            "export", "-t", "src", "-n", "guard", "--yes", "--force",
            check=True,
        )
        self.assertEqual(forced.returncode, 0)
        self.assertNotEqual(self.workspace_file("guard").read_bytes(), before)

        # Same window/pane counts, but a running pane becomes idle.
        self.run_tmux(
            "new-session", "-d", "-s", "cmd", "-n", "one", "-c", str(self.proj)
        )
        cmd_pane = self.pane_map("cmd")[(0, 0)]
        self.run_tmux(
            "set", "-p", "-t", cmd_pane, "@tm_command", "sleep 60"
        )
        self.run_tool("export", "-t", "cmd", "-n", "idleguard", check=True)

        self.run_tmux(
            "new-session", "-d", "-s", "idle", "-n", "one", "-c", str(self.proj)
        )
        idle_guard = self.run_tool(
            "export", "-t", "idle", "-n", "idleguard", "--yes"
        )
        self.assertNotEqual(idle_guard.returncode, 0)
        self.assertIn("idle", idle_guard.stderr)

    def test_running_session_never_replaced(self) -> None:
        self.make_source()
        self.run_tool("export", "-t", "src", "-n", "src", check=True)
        before = self.tmux_lines(
            "list-panes", "-s", "-t", "src", "-F", "#{pane_id}"
        )

        refused = self.run_tool("restore", "src", "--yes")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("Refusing to overwrite", refused.stderr)

        after = self.tmux_lines(
            "list-panes", "-s", "-t", "src", "-F", "#{pane_id}"
        )
        self.assertEqual(before, after)

    def test_keep_and_catalog(self) -> None:
        self.make_source()
        for _ in range(3):
            self.run_tool(
                "export", "-t", "src", "-n", "keepme", "--keep", "2",
                check=True,
            )

        workspaces = self.data / "workspaces"
        base = workspaces / "keepme.yaml"
        self.assertTrue(base.exists())
        dated = [
            path
            for path in workspaces.glob("keepme.*.yaml")
            if path != base
        ]
        self.assertEqual(len(dated), 2, [path.name for path in dated])
        for path in dated:
            self.assertRegex(
                path.name,
                r"^keepme\.\d{4}-\d{2}-\d{2}T\d{4}(\d{2})?(-\d+)?\.yaml$",
            )

        catalog = self.run_tool("restore", input_text="", check=True)
        self.assertIn("keepme", catalog.stdout)
        self.assertNotIn("keepme.20", catalog.stdout)

    def test_diff(self) -> None:
        self.make_source()
        self.run_tool("export", "-t", "src", "-n", "demo", check=True)

        same = self.run_tool("diff", "demo")
        self.assertEqual(same.returncode, 0, same.stderr)
        self.assertIn("No differences", same.stdout)

        self.run_tmux(
            "new-window", "-t", "src:7", "-n", "extra", "-c", str(self.proj)
        )
        extra = self.pane_map("src")[(7, 0)]
        self.run_tmux("set", "-p", "-t", extra, "@tm_command", "vim notes.txt")
        self.run_tmux(
            "set", "-p", "-t", self.pane_map("src")[(0, 1)],
            "@tm_command", "htop"
        )

        changed = self.run_tool("diff", "demo")
        self.assertEqual(changed.returncode, 1, changed.stderr)
        self.assertIn("+ window 7", changed.stdout)
        self.assertIn("~ window 0 pane 1", changed.stdout)
        self.assertIn("htop", changed.stdout)

    def test_check(self) -> None:
        workspaces = self.data / "workspaces"
        workspaces.mkdir(parents=True)
        missing = self.tmp / "does-not-exist"
        risky = {
            "workspace": "risky",
            "windows": [
                {
                    "name": "code",
                    "index": 0,
                    "panes": [
                        {
                            "index": 0,
                            "cwd": str(missing),
                            "command": "python",
                        },
                        {
                            "index": 1,
                            "cwd": str(self.proj),
                            "command": "DB_PASSWORD=hunter2 ./run.sh",
                        },
                        {
                            "index": 2,
                            "cwd": str(self.proj),
                            "command": "gunicorn -b 0.0.0.0:8000",
                            "guessed": True,
                        },
                    ],
                }
            ],
        }
        (workspaces / "risky.yaml").write_text(
            yaml.safe_dump(risky, sort_keys=False), encoding="utf-8"
        )

        result = self.run_tool("check", "risky")
        self.assertEqual(result.returncode, 1)
        self.assertIn("folder does not exist", result.stdout)
        self.assertIn("bare interpreter/server without a script: python",
                      result.stdout)
        self.assertIn("may contain a password, token, or key", result.stdout)
        self.assertIn("command was guessed", result.stdout)
        self.assertIn("bare interpreter/server without a script: gunicorn",
                      result.stdout)

        clean = {
            "workspace": "clean",
            "windows": [
                {
                    "name": "code",
                    "index": 0,
                    "panes": [
                        {
                            "index": 0,
                            "cwd": str(self.proj),
                            "command": "./run.sh",
                        },
                        {
                            "index": 1,
                            "cwd": str(self.proj),
                            "command": "python -m http.server",
                        },
                        {
                            "index": 2,
                            "cwd": str(self.proj),
                            "command": "gunicorn app:app",
                        },
                    ],
                }
            ],
        }
        (workspaces / "clean.yaml").write_text(
            yaml.safe_dump(clean, sort_keys=False), encoding="utf-8"
        )
        clean_result = self.run_tool("check", "clean")
        self.assertEqual(clean_result.returncode, 0, clean_result.stdout)
        self.assertIn("No warnings", clean_result.stdout)

    def test_install_hook(self) -> None:
        bashrc = self.home / ".bashrc"
        zshrc = self.home / ".zshrc"
        bashrc.write_text('alias ll="ls -l"\n', encoding="utf-8")
        zshrc.write_text("setopt promptsubst\n", encoding="utf-8")

        result = self.run_tool("install-hook", check=True)
        self.assertIn("not in PATH", result.stderr)
        self.assertIn(str(TOOL.resolve()), result.stderr)

        for path in (bashrc, zshrc):
            text = path.read_text(encoding="utf-8")
            self.assertEqual(text.count("# >>> tmux-manager hook >>>"), 1)
            self.assertEqual(text.count("# <<< tmux-manager hook <<<"), 1)
        bash_text = bashrc.read_text(encoding="utf-8")
        self.assertIn("DEBUG", bash_text)
        self.assertIn("PROMPT_COMMAND", bash_text)
        zsh_text = zshrc.read_text(encoding="utf-8")
        self.assertIn("preexec", zsh_text)
        self.assertIn("precmd", zsh_text)
        self.assertIn('alias ll="ls -l"', bash_text)
        self.assertIn("setopt promptsubst", zsh_text)

        subprocess.run(
            ["bash", "-n", str(bashrc)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if shutil.which("zsh"):
            subprocess.run(
                ["zsh", "-n", str(zshrc)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.run_tool("install-hook", check=True)
        self.assertEqual(
            bashrc.read_text(encoding="utf-8").count(
                "# >>> tmux-manager hook >>>"
            ),
            1,
        )

        self.run_tool("install-hook", "--remove", check=True)
        for path, original in (
            (bashrc, 'alias ll="ls -l"\n'),
            (zshrc, "setopt promptsubst\n"),
        ):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("tmux-manager hook", text)
            self.assertEqual(text, original)

    def test_install_boot(self) -> None:
        fake_bin = self.tmp / "bin"
        fake_bin.mkdir()
        crontab_file = self.tmp / "crontab.txt"
        fake_crontab = fake_bin / "crontab"
        fake_crontab.write_text(
            "#!/bin/sh\n"
            'if [ "$1" = "-l" ]; then\n'
            '  [ -f "$FAKE_CRONTAB" ] || { echo "no crontab for user" >&2; exit 1; }\n'
            '  cat "$FAKE_CRONTAB"\n'
            'elif [ "$1" = "-" ]; then\n'
            '  cat > "$FAKE_CRONTAB"\n'
            "else\n"
            "  exit 2\n"
            "fi\n",
            encoding="utf-8",
        )
        fake_crontab.chmod(0o755)
        crontab_file.write_text('MAILTO=""\n', encoding="utf-8")
        env_extra = {
            "PATH": f"{fake_bin}{os.pathsep}{self.env['PATH']}",
            "FAKE_CRONTAB": str(crontab_file),
        }
        log_path = self.tmp / "logs" / "demo.log"

        result = self.run_tool(
            "install-boot",
            "demo",
            "--delay",
            "5",
            "--log",
            str(log_path),
            env_extra=env_extra,
            check=True,
        )
        self.assertIn("not in PATH", result.stderr)
        text = crontab_file.read_text(encoding="utf-8")
        self.assertIn('MAILTO=""', text)
        self.assertIn("# tmux-manager boot: demo", text)
        self.assertIn("@reboot sleep 5 && ", text)
        self.assertIn(str(TOOL.resolve()), text)
        self.assertIn("restore demo --if-missing --yes", text)
        self.assertIn(f"--log {log_path}", text)
        self.assertEqual(text.count("# tmux-manager boot: demo"), 1)

        self.run_tool(
            "install-boot",
            "demo",
            "--delay",
            "9",
            "--log",
            str(log_path),
            env_extra=env_extra,
            check=True,
        )
        text = crontab_file.read_text(encoding="utf-8")
        self.assertEqual(text.count("# tmux-manager boot: demo"), 1)
        self.assertIn("@reboot sleep 9 && ", text)
        self.assertNotIn("@reboot sleep 5", text)

        self.run_tool(
            "install-boot", "demo", "--remove", env_extra=env_extra, check=True
        )
        text = crontab_file.read_text(encoding="utf-8")
        self.assertNotIn("tmux-manager boot", text)
        self.assertNotIn("@reboot", text)
        self.assertIn('MAILTO=""', text)

        self.run_tool(
            "install-boot", "other", env_extra=env_extra, check=True
        )
        self.run_tool("install-boot", "--remove",
                      env_extra=env_extra, check=True)
        text = crontab_file.read_text(encoding="utf-8")
        self.assertNotIn("tmux-manager boot", text)
        self.assertIn('MAILTO=""', text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
