# tmux-session-manager

Save a tmux workspace as YAML and restore it later.

`tmux-manager` records the exact commands typed in each pane, then recreates the
same session: window indexes, duplicate and unusual window names, folders,
layouts, active windows, active panes, zoomed panes, pane titles, and the
commands themselves. It also refuses to replace a running session.

```bash
tmux-manager --help
tmux-manager export --help
tmux-manager restore --help
```

## Commands

| Command | What it does |
| --- | --- |
| `tmux-manager ls` | List live panes with their folders and commands |
| `tmux-manager export` | Save the current (or `-t`) session as YAML |
| `tmux-manager restore` | Pick, preview, and restore a saved workspace |
| `tmux-manager diff NAME` | Compare a saved snapshot with the live session |
| `tmux-manager check NAME` | Inspect a snapshot and warn about risky commands |
| `tmux-manager install-hook` | Record the exact command typed in each pane |
| `tmux-manager install-boot NAME` | Restore a workspace at boot with `@reboot` |
| `tmux-manager install-hook --remove` | Remove the shell hook |
| `tmux-manager install-boot NAME --remove` | Remove the boot entry |

Older names still work: `tmux-status`, `tmux-export`, `tmux-restore`.

## Everyday use

```bash
tmux-manager ls                 # live tmux panes
tmux-manager export             # save current session
tmux-manager restore            # pick from saved workspaces
tmux-manager restore my-project # preview, then confirm
```

Exports land in `~/.local/share/tmux-manager/workspaces/` (or
`$XDG_DATA_HOME/tmux-manager/workspaces`). You do not have to remember a file
path. `TMUX_MANAGER_HOME` overrides the data folder entirely.

`tmux-manager restore` with no name lists what is saved: name, window count,
pane count, and window names. Choosing one (or passing a name) prints a preview
of directories and commands, then asks before creating the session.

If that session is already running, restore **does not replace it**. The live
session is left untouched. You can attach to it, or restore a copy under
another name:

```bash
tmux attach -t my-project
tmux-manager restore my-project --as my-project-copy
```

```bash
tmux-manager export -t other-session
tmux-manager restore my-project -y
tmux-manager restore my-project --no-commands
tmux-manager export -o ./work.yaml     # custom path if you need it
```

---

## Exact commands: install the shell hook

Without help, a tool can only guess a pane's command from the process tree.
That guess is useful but not always exact. Install the hook once to record the
command **exactly as typed**, including `VAR=value` prefixes, quotes, and
arguments with spaces.

```bash
tmux-manager install-hook
```

This adds one small block to `~/.bashrc` and `~/.zshrc`. The block is only
active inside tmux and only in an interactive shell.

- **bash** installs a `DEBUG` trap that stores the command line in the pane
  option `@tm_command` as it starts. `PROMPT_COMMAND` clears it when the prompt
  returns.
- **zsh** uses `preexec` and `precmd` to do the same.

The hook ignores its own commands, prompt commands, commands run in subshells,
and background jobs (the option is cleared when the prompt returns). Open a new
shell in a tmux pane, or source the rc file, to start recording.

bash has only one `DEBUG` trap. `install-hook` replaces an existing `DEBUG`
trap; if you already use one for something else, merge the two traps instead of
installing blindly.

Remove it again with:

```bash
tmux-manager install-hook --remove
```

If the shell started by tmux is a login shell, make sure it loads `.bashrc`
(for example by sourcing it from `.bash_profile`). Otherwise the hook never
runs.

Export prefers `@tm_command`. Only when it is empty does it fall back to
guessing. A guessed command is marked so you can review it:

```yaml
command: sleep 300
guessed: true
```

### Guessing without the hook

Without a hook, export takes the **oldest** child of the pane's shell
(`pgrep -P <pane_pid> -o`) and reads its process arguments. The oldest child is
used on purpose: a background job started later must not replace the program
that was launched in the foreground. If the pane itself is not a shell (a
program was started directly), the pane process arguments are used.

### The `exec` caveat

A script ending in `exec` replaces the script process with the final program.
The old guess then sees only the final program, not the script name. For
example, `./run.sh` that ends with `exec python manage.py runserver` may be
saved as `python manage.py runserver`. The shell hook avoids this because it
records the typed line before the script starts.

---

## Export

```bash
tmux-manager export [-t SESSION] [-n NAME] [-o FILE]
                    [--no-commands] [--keep N] [--yes] [--force]
```

- `-t/--session` exports another session instead of the current one.
- `-n/--name` sets the workspace name; the default is the session name.
- `-o/--output` writes a custom file instead of the workspaces folder.
- `--no-commands` saves layout, folders, titles, and active panes only;
  every pane gets `command: ''`. It is the export-side counterpart of
  `restore --no-commands`.
- `--keep N` also writes dated copies next to the snapshot, such as
  `my-project.2026-10-30T1553.yaml`, and keeps the newest `N` of them.
  `my-project.yaml` always remains the current snapshot. `restore` and the
  catalog only use `my-project.yaml`.
- `--yes` skips the overwrite question below. It does **not** force an
  overwrite.
- `--force` overwrites even when the new snapshot is worse.

### The snapshot guard

Before overwriting an existing snapshot, export compares the old and new data.
It warns and asks when the new snapshot:

- has fewer windows,
- has fewer panes, or
- turns panes that had a command into idle panes.

In a terminal it asks `Overwrite anyway?`. With `--yes` (or when no terminal is
attached) it refuses and exits non-zero. Use `--force` to save the smaller
snapshot anyway. This makes a cron or timer snapshot safe: it cannot silently
replace a good workspace with an empty one.

### Dated copies

```bash
tmux-manager export --keep 10
```

Each export writes the current snapshot to `name.yaml` and a dated copy such as
`name.2026-10-30T1553.yaml`. Older dated copies beyond `--keep` are removed.
The catalog ignores dated copies. If a dated copy for the same minute already
exists, a numeric suffix is added (`name.2026-10-30T1553-2.yaml`), so a fast
repeated export never overwrites a copy from the same minute.

---

## Restore

```bash
tmux-manager restore [NAME|FILE]
                    [--no-commands] [--yes] [--as NAME]
                    [--if-missing | --missing-windows]
                    [--log FILE]
```

- `--no-commands` recreates structure and folders only; no pane command is
  sent and no `delay`/`wait_for` is waited for.
- `-y/--yes` skips the confirmation prompt.
- `--as NAME` restores under another session name.
- `--if-missing` does nothing and exits `0` when the session already exists.
  It is safe to run on every boot.
- `--missing-windows` adds back only windows whose saved index is missing from
  a running session. Live windows are not changed. If the session is not
  running, it performs a normal restore.
- `--log FILE` appends timestamps and every action/warning to a file. Parent
  folders are created. This is what `install-boot` uses.

Exit codes: `0` means restored, or nothing to do (`--if-missing` with a live
session, `--missing-windows` with no gaps). A non-zero code means an error or a
refused overwrite. Cancelling a prompt is `0`.

### Structure is restored exactly

- Windows are recreated at their saved index with
  `new-window -t session:<index>`, so gaps stay gaps.
- Duplicate window names are kept. Names with spaces or punctuation such as
  `PSR Website:` are passed through unchanged.
- The active window is selected again.
- The active pane in each window is selected again.
- Zoomed windows are zoomed on their saved active pane.
- Pane titles are restored.
- Each window's saved layout is applied after all its panes exist.

The layout string includes old pane ids. tmux maps the saved geometry onto the
new panes; the window sizes, split positions, and pane count are what matter.

### Missing folders are safe

If a pane's saved folder no longer exists, the pane is created in `$HOME`
instead, its command is **not** sent, and a warning names the window, pane, and
folder:

```text
warning: window 'api' (index 2), pane 1: folder '/srv/old-api' does not exist;
creating the pane in /home/you and not sending its command
```

This guarantees a command never runs in the wrong folder.

### Safe pane startup

After a pane is created, restore waits until its shell is ready before sending
anything: the pane process must be a shell and its startup files must have
finished. This avoids lost keystrokes with a slow `.bashrc`.

Two optional per-pane YAML keys make apps wait for their dependencies:

```yaml
panes:
  - index: 0
    cwd: /home/you/shop
    command: ./run-api.sh
    delay: 1.5                 # seconds after the shell is ready
    wait_for: 127.0.0.1:5432   # host:port, or a file path
    wait_timeout: 60           # seconds (default 60)
```

`wait_for` may be a single value or a list. `127.0.0.1:5432` and
`127.0.0.1:6379` wait for a TCP port; a value starting with `/`, `.`, or `~`
(and anything that is not `host:port`) waits for a file to exist. Items are
checked in order: shell ready, `delay`, then every `wait_for`. A timeout prints
a warning and still starts the command. `wait_timeout` overrides the default.

---

## Compare a snapshot with the live session

```bash
tmux-manager diff my-project
```

This compares the saved `my-project.yaml` with the live session of the same
name (or its `source_session`). It shows:

- windows only in the snapshot (`-`) or only live (`+`),
- changed window names and layouts,
- changed folders and commands,
- changed active window, active pane, and zoom state.

Exit code `0` means no differences; `1` means something changed. This is handy
before overwriting a snapshot: see what happened since it was saved.

---

## Check a snapshot

```bash
tmux-manager check my-project
```

`check` lists every window and pane with its folder and command, then warns
about:

- folders that no longer exist,
- commands marked `guessed: true`,
- bare interpreters or servers started without a script: `python`, `node`,
  `celery`, `gunicorn`, `uvicorn`,
- command lines that look like they contain a password, token, or key.

Exit code `1` means at least one warning was found. It never runs anything.

Snapshots are plain YAML. A command line can contain a secret even when `check`
does not recognize it, so treat the workspaces folder like shell history and
protect it accordingly.

---

## Boot setup

```bash
tmux-manager install-boot my-project
tmux-manager install-boot my-project --delay 30 --log ~/tmux-restore.log
tmux-manager install-boot my-project --remove
tmux-manager install-boot --remove            # remove every boot entry
```

This adds one pair of lines to your crontab:

```cron
# tmux-manager boot: my-project
@reboot sleep 15 && /home/you/.local/bin/tmux-manager restore my-project --if-missing --yes --log /home/you/.local/share/tmux-manager/logs/my-project.log
```

The full path to `tmux-manager` is used, so cron does not need your shell
`PATH`. `--delay` is configurable (default 15 seconds) and `--log` defaults to
the data folder's `logs/<name>.log`.

Because the restore uses `--if-missing`, a session that is already running is
never touched. To fill in windows that disappeared after a crash, run:

```bash
tmux-manager restore my-project --missing-windows --yes
```

`install-boot` and `install-hook` warn when `~/.local/bin` is not on `PATH` and
print the full path to use. Cron has a minimal `PATH`; if your `tmux` or
`python3` lives somewhere unusual, add a `PATH=` line to the crontab. If you
use `TMUX_MANAGER_HOME`, add that assignment to the crontab too, because cron
does not read your shell configuration.

---

## Storage and paths

Workspaces are stored in a fixed folder, independent of the current directory:

```text
$TMUX_MANAGER_HOME/workspaces
$XDG_DATA_HOME/tmux-manager/workspaces
~/.local/share/tmux-manager/workspaces
```

When restoring by name, only the workspaces folder is searched. A file in the
current directory is used only when you pass a path explicitly:

```bash
tmux-manager restore my-project             # workspaces folder
tmux-manager restore ./my-project.yaml      # explicit file
tmux-manager restore /tmp/work.yaml         # explicit file
```

A bare name never picks up a stray `my-project.yaml` from the current folder.

---

## Installation

The recommended installation keeps the **Git repository itself in
`~/.local/bin`**. This avoids putting a project directory such as
`~/tmux-session-manager` in your home directory, while keeping updates simple.

`~/.local/bin` is a standard user-local executable directory and is commonly
already in `PATH`. The installation creates symlinks for the commands, so there
are no duplicate copies to keep in sync.

```bash
git clone https://github.com/legeRise/tmux-session-manager.git ~/.local/bin/tmux-session-manager
cd ~/.local/bin/tmux-session-manager
chmod +x tmux-manager tmux-*

ln -s ~/.local/bin/tmux-session-manager/tmux-manager ~/.local/bin/tmux-manager
ln -s ~/.local/bin/tmux-session-manager/tmux-status ~/.local/bin/tmux-status
ln -s ~/.local/bin/tmux-session-manager/tmux-export ~/.local/bin/tmux-export
ln -s ~/.local/bin/tmux-session-manager/tmux-restore ~/.local/bin/tmux-restore
```

After installation, use the CLI from anywhere:

```bash
tmux-manager ls
tmux-manager install-hook       # exact commands
tmux-manager install-boot work  # optional: restore at boot
```

To update the tool later, update the repository directly:

```bash
cd ~/.local/bin/tmux-session-manager
git pull
```

The symlinks continue pointing to the repository files, so the updated version
is used immediately. You can also inspect or modify the source normally because
it remains a regular Git repository.

If `~/.local/bin` is not in your `PATH`, add it using your shell's normal
configuration. Most Linux desktop environments already include it for
user-local executables. The installers print the full path to use when it is
missing.

## Requirements

- Linux/macOS
- tmux
- Python 3
- PyYAML

```bash
pip install pyyaml
```

---

## YAML example

```yaml
workspace: my-project
source_session: my-project
active_window: 2
windows:
  - name: code
    index: 0
    layout: 1a2b,160x40,0,0{80x40,0,0,1,80x40,81,0,2}
    active_pane: 1
    panes:
      - index: 0
        cwd: /home/you/my-project
        command: vim
        title: editor
      - index: 1
        cwd: /home/you/my-project
        command: './run.sh --port 8000'
        guessed: true
  - name: 'PSR Website:'
    index: 2
    layout: 1a2c,160x40,0,0,3
    zoomed: true
    active_pane: 0
    panes:
      - index: 0
        cwd: /home/you/psr
        command: ./run-api.sh
        delay: 1
        wait_for: 127.0.0.1:5432
        wait_timeout: 60
```

Every key except `workspace` and `windows` is optional. Older YAML files with
only `name`, `index`, `layout`, `panes`, `cwd`, and `command` still load and
restore. Missing `active_window`, `active_pane`, `zoomed`, `title`, `guessed`,
`delay`, and `wait_for` simply mean "nothing saved".

YAML is written and read with PyYAML, so commands and paths are escaped instead
of pasted as raw text.

---

## Tests

The tests use a private tmux server (`TMUX_TMPDIR`) and a private
`TMUX_MANAGER_HOME`, so they never touch real sessions or workspaces:

```bash
python3 -m unittest discover -s tests -v
```

They cover export/restore round trips (names, indexes, folders, layouts,
active and zoomed panes, titles, exact commands), `--no-commands` on export and
restore, missing folders, `--if-missing`, `--missing-windows`, the snapshot
guard, dated snapshots, `diff`, `check`, the shell hook installer, the boot
installer, and that a running session is never replaced.

---

## Version

### v1.2

- Shell hook records the exact typed command in `@tm_command` (bash `DEBUG`
  trap, zsh `preexec`), with `install-hook` / `--remove`
- Export prefers the hook and saves `guessed: true` for process-tree guesses
- Guessing uses the oldest child, not the newest
- `export --no-commands` and `restore --no-commands`
- Restore keeps window indexes, duplicate/special names, active window, active
  pane, zoom, titles, and layouts
- Missing folders create the pane in `$HOME` and skip the command
- Shell-ready waiting plus `delay`, `wait_for`, and `wait_timeout`
- `restore --if-missing`, `--missing-windows`, `--log`, meaningful exit codes
- `export --keep N`, dated snapshots, and the smaller/idle snapshot guard
- `tmux-manager diff` and `tmux-manager check`
- `install-boot` with configurable delay, log, and removal
- Name lookup uses the workspaces folder, not the current directory
- Tests and documentation for all of the above

### v1.1

- Single CLI: `tmux-manager ls|export|restore`
- Safe YAML dump/load
- Restore targets panes by id (`-P -F`) and reapplies window layout
- `ls` groups session, window name, and pane
- Documented `run.sh` workflow instead of capturing env/args
- Default workspace directory, restore catalog, and restore preview

### v1.0

Save a tmux workspace and restore it later.

---

## Later

Possible next step: a periodic snapshot (`cron` / systemd timer) that runs
`tmux-manager export -t SESSION --keep 24` so the folder keeps a day of
history. The snapshot guard already protects the current snapshot from a bad
run.

Not in this version: environment variable capture, automatic virtualenv
activation, argument reconstruction for processes launched outside the shell.

---

## Why?

tmux is a good workspace. Rebuilding it after a reboot or a new machine is not.
This keeps the workspace as a portable file, and keeps runtime details in
project scripts you already understand.
