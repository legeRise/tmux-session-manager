# tmux-session-manager

Save a tmux workspace as YAML and restore it later.

The CLI is `tmux-manager`. It lists sessions, exports a session to a file, and recreates windows, panes, directories, and a best-effort command.

```bash
tmux-manager --help
tmux-manager export --help
tmux-manager restore --help
```

## Everyday use

```bash
tmux-manager ls                 # live tmux sessions
tmux-manager export             # save current session
tmux-manager restore            # pick from saved workspaces
tmux-manager restore my-project # preview, then confirm
```

Exports land in `~/.local/share/tmux-manager/workspaces/` (or `$XDG_DATA_HOME/tmux-manager/workspaces`). You do not have to remember a file path.

`tmux-manager restore` with no name lists what is saved: name, window count, pane count, and window names. Choosing one (or passing a name) prints a preview of directories and commands, then asks before creating the session.

If that session is already running, restore **does not replace it**. The live session is left untouched. You can attach to it, or restore a copy under another name:

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

Set `TMUX_MANAGER_HOME` to store files somewhere else.

Older names still work: `tmux-status`, `tmux-export`, `tmux-restore`.

---

## How to run things (important)

This tool does **not** try to capture every environment variable, virtualenv, port flag, or shell quirk. That path is fragile, and a missed env var looks like a successful restore until something breaks.

Put the real process behind a small script in the project, then leave that script running in the pane:

```bash
./run.sh
./local.sh
./production.sh
./deploy.sh
```

Example `run.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export PORT=8000
export APP_ENV=local
source .venv/bin/activate
exec python manage.py runserver "$PORT"
```

Export will see `./run.sh` (or `bash run.sh`). Restore sends that same command. Ports, secrets, venvs, and flags stay in your script, not in tmux YAML.

If a pane is only a shell, export stores an empty command and restore leaves it idle.

---

## Installation

The recommended installation keeps the **Git repository itself in `~/.local/bin`**. This avoids putting a project directory such as `~/tmux-session-manager` in your home directory, while keeping updates simple.

`~/.local/bin` is a standard user-local executable directory and is commonly already in `PATH`. The installation creates symlinks for the commands, so there are no duplicate copies to keep in sync.

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
```

To update the tool later, update the repository directly:

```bash
cd ~/.local/bin/tmux-session-manager
git pull
```

The symlinks continue pointing to the repository files, so the updated version is used immediately. You can also inspect or modify the source normally because it remains a regular Git repository.

If `~/.local/bin` is not in your `PATH`, add it using your shell's normal configuration. Most Linux desktop environments already include it for user-local executables.

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
windows:
  - name: code
    index: 0
    layout: 1a2b,160x40,0,0{80x40,0,0,1,80x40,81,0,2}
    panes:
      - index: 0
        cwd: /home/you/my-project
        command: vim
      - index: 1
        cwd: /home/you/my-project
        command: ./run.sh
```

YAML is written and read with PyYAML, so commands and paths are escaped instead of pasted as raw text.

---

## Version

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

Possible next step: a periodic snapshot (`cron` / systemd timer) that runs `tmux-manager export -t SESSION` so the file in the workspaces folder stays fresh.

Not in this version: env capture, auto-venv, argument reconstruction.

---

## Why?

tmux is a good workspace. Rebuilding it after a reboot or a new machine is not. This keeps the workspace as a portable file, and keeps runtime details in project scripts you already understand.
