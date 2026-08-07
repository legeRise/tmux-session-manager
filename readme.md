# tmux-session-manager

Simple tmux tools to save, restore, and manage terminal sessions.

This project helps you capture your current tmux workspace and recreate it later.

## Features

### tmux-status

View your current tmux workspace:

- windows
- panes
- running commands
- project directories
- pane status

Example:

```bash
tmux-status
```

---

### tmux-export

Export your current tmux session into a YAML workspace file.

Example:

```bash
tmux-export
```

This creates a file like:

```text
my-project.yaml
```

The export contains:

- session name
- windows
- panes
- working directories
- running commands

---

### tmux-restore

Restore a workspace from an exported YAML file.

Example:

```bash
tmux-restore my-project.yaml
```

It will recreate:

- tmux session
- windows
- panes
- directories
- commands

---

# Installation

Clone the repository:

```bash
git clone https://github.com/legeRise/tmux-session-manager.git
cd tmux-session-manager
```

Make scripts executable:

```bash
chmod +x tmux-*
```

Optional: install globally:

```bash
cp tmux-* ~/.local/bin/
```

Now you can run:

```bash
tmux-status
tmux-export
tmux-restore
```

from anywhere.

---

# Requirements

- Linux/macOS
- tmux
- Python 3
- PyYAML

Install PyYAML:

```bash
pip install pyyaml
```

---

# Version

## v1.0

This is the first version of tmux-session-manager.

The goal of v1 is simple:

> Save a tmux workspace and restore it later.

---

# Known Limitations

`tmux-export` works well for normal commands, but v1 has some limitations.

## Environment variables are not captured

Commands that depend on temporary environment variables will not restore correctly.

Example:

Works:

```bash
python manage.py runserver
```

May not work:

```bash
PORT=8000 python main.py
```

because the `PORT=8000` environment variable is not saved.

---

## Command arguments may have limitations

Commands like:

```bash
python main.py --host 0.0.0.0 --port 8000
```

may need manual adjustment after restore depending on the application.

---

## Future improvements

Planned improvements:

- capture environment variables
- better shell handling
- support virtual environments automatically
- improve command restoration
- add safer YAML handling
- better cross-platform support

---

# Why?

tmux is already a powerful workspace manager, but after losing a server session or moving machines, rebuilding everything manually is annoying.

This project tries to make tmux workspaces portable.