#!/usr/bin/env python3
from __future__ import annotations
"""
notes — neovim-style TUI note taker with GitHub sync, multi-select, and pin
Usage: notes
"""

import json
import base64
import threading
from datetime import datetime
from pathlib import Path
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import ListView, ListItem, Label, TextArea, Static, Footer, Input
from textual.containers import Horizontal, Vertical, Center, Middle
from textual.reactive import reactive
from textual.screen import ModalScreen, Screen

# ══════════════════════════════════════════════════════════════════════════════
#  THEME  —  edit hex values to customize
#
#  Presets:
#    Gruvbox:    bg="#282828"  accent="#fabd2f"  accent2="#b8bb26"  red="#fb4934"
#    Catppuccin: bg="#1e1e2e"  accent="#cba6f7"  accent2="#89dceb"  red="#f38ba8"
#    Rose Pine:  bg="#191724"  accent="#c4a7e7"  accent2="#9ccfd8"  red="#eb6f92"
#    Nord:       bg="#2e3440"  accent="#88c0d0"  accent2="#81a1c1"  red="#bf616a"
# ══════════════════════════════════════════════════════════════════════════════

THEME = {
    "bg":           "#1a1b26",
    "bg_dark":      "#16161e",
    "bg_highlight": "#292e42",
    "border":       "#3b4261",
    "border_hl":    "#7aa2f7",
    "fg":           "#c0caf5",
    "fg_dim":       "#565f89",
    "fg_dark":      "#3b4261",
    "accent":       "#7aa2f7",
    "accent2":      "#bb9af7",
    "accent3":      "#7dcfff",
    "green":        "#9ece6a",
    "yellow":       "#e0af68",
    "red":          "#f7768e",
    "orange":       "#ff9e64",
}

LOGO = r"""
 ███╗   ██╗ ██████╗ ████████╗███████╗███████╗
 ████╗  ██║██╔═══██╗╚══██╔══╝██╔════╝██╔════╝
 ██╔██╗ ██║██║   ██║   ██║   █████╗  ███████╗
 ██║╚██╗██║██║   ██║   ██║   ██╔══╝  ╚════██║
 ██║ ╚████║╚██████╔╝   ██║   ███████╗███████║
 ╚═╝  ╚═══╝ ╚═════╝    ╚═╝   ╚══════╝╚══════╝"""

# ══════════════════════════════════════════════════════════════════════════════
#  Storage & config
# ══════════════════════════════════════════════════════════════════════════════

DATA_DIR    = Path.home() / ".local" / "share" / "notes-tui"
DATA_FILE   = DATA_DIR / "notes.json"
CONFIG_FILE = DATA_DIR / "config.json"


def load_config() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_config(cfg: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)
    CONFIG_FILE.chmod(0o600)


def load_notes() -> list[dict]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_notes(notes: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(notes, f, indent=2)


def sorted_notes(notes: list[dict]) -> list[dict]:
    """Pinned notes always float to the top, then sort by modified desc."""
    return sorted(notes, key=lambda n: (not n.get("pinned", False), n.get("modified", "")), reverse=False)


def new_note() -> dict:
    now = datetime.now().isoformat(timespec="seconds")
    return {"id": now, "title": "Untitled", "body": "", "created": now, "modified": now, "pinned": False}


def fmt_date(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        today = datetime.now().date()
        if dt.date() == today:
            return dt.strftime("%-I:%M %p")
        elif dt.year == today.year:
            return dt.strftime("%b %-d")
        else:
            return dt.strftime("%b %-d, %Y")
    except Exception:
        return iso[:10]


# ══════════════════════════════════════════════════════════════════════════════
#  GitHub sync
# ══════════════════════════════════════════════════════════════════════════════

class GitHubSync:
    FILENAME = "notes.json"

    def __init__(self, token: str, username: str, repo: str):
        self.token    = token
        self.username = username
        self.repo     = repo
        self._base    = f"https://api.github.com/repos/{username}/{repo}/contents/{self.FILENAME}"
        self._headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
        }

    def _get_sha(self) -> str | None:
        try:
            import urllib.request
            req = urllib.request.Request(self._base, headers=self._headers)
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read()).get("sha")
        except Exception:
            return None

    def push(self, notes: list[dict]) -> tuple[bool, str]:
        try:
            import urllib.request
            content = base64.b64encode(json.dumps(notes, indent=2).encode()).decode()
            sha = self._get_sha()
            payload: dict = {
                "message": f"sync: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                "content": content,
            }
            if sha:
                payload["sha"] = sha
            req = urllib.request.Request(
                self._base, data=json.dumps(payload).encode(),
                headers=self._headers, method="PUT"
            )
            with urllib.request.urlopen(req):
                return True, "synced"
        except Exception as e:
            return False, str(e)

    def pull(self) -> tuple[list[dict] | None, str]:
        try:
            import urllib.request
            req = urllib.request.Request(self._base, headers=self._headers)
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read())
                raw = base64.b64decode(data["content"]).decode()
                return json.loads(raw), "pulled"
        except Exception as e:
            return None, str(e)

    @staticmethod
    def ensure_repo_exists(token: str, username: str, repo: str) -> tuple[bool, str]:
        try:
            import urllib.request, urllib.error
            headers = {
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github+json",
            }
            req = urllib.request.Request(
                f"https://api.github.com/repos/{username}/{repo}", headers=headers
            )
            try:
                urllib.request.urlopen(req)
                return True, "exists"
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    return False, f"HTTP {e.code}"
            payload = json.dumps({
                "name": repo, "private": True,
                "description": "notes-tui sync", "auto_init": True,
            }).encode()
            urllib.request.urlopen(urllib.request.Request(
                "https://api.github.com/user/repos",
                data=payload, headers=headers, method="POST"
            ))
            return True, "created"
        except Exception as e:
            return False, str(e)


# ══════════════════════════════════════════════════════════════════════════════
#  CSS
# ══════════════════════════════════════════════════════════════════════════════

def make_css() -> str:
    t = THEME
    return f"""
    Screen {{ background: {t['bg']}; }}

    /* ── Splash ── */
    #logo {{
        color: {t['accent']}; text-style: bold;
        content-align: center middle; width: auto; padding-bottom: 1;
    }}
    #tagline {{
        color: {t['fg_dim']}; content-align: center middle;
        width: auto; padding-bottom: 2;
    }}
    #menu-wrap {{ width: 42; height: auto; }}
    .menu-item {{
        height: 1; color: {t['fg_dim']}; width: 42; padding: 0 2;
    }}
    .menu-selected {{
        height: 1; color: {t['accent']}; text-style: bold;
        width: 42; padding: 0 2; background: {t['bg_highlight']};
    }}
    #splash-hint {{
        color: {t['fg_dark']}; content-align: center middle;
        width: auto; padding-top: 2;
    }}
    #splash-version {{
        color: {t['fg_dark']}; content-align: center middle;
        width: auto; padding-top: 1;
    }}

    /* ── Setup ── */
    #setup-box {{
        width: 60; height: auto; background: {t['bg_dark']};
        border: solid {t['accent']}; padding: 2 4;
    }}
    #setup-title {{
        color: {t['accent']}; text-style: bold;
        content-align: center middle; width: 100%; margin-bottom: 1;
    }}
    #setup-sub {{
        color: {t['fg_dim']}; content-align: center middle;
        width: 100%; margin-bottom: 2;
    }}
    .setup-label {{ color: {t['fg_dim']}; margin-top: 1; }}
    .setup-input {{
        background: {t['bg']}; color: {t['fg']};
        border: solid {t['border']}; margin-bottom: 1;
    }}
    .setup-input:focus {{ border: solid {t['accent']}; }}
    #setup-status {{
        color: {t['yellow']}; content-align: center middle;
        width: 100%; margin-top: 1; height: 1;
    }}
    #setup-hint {{
        color: {t['fg_dark']}; content-align: center middle;
        width: 100%; margin-top: 2;
    }}

    /* ── Sidebar ── */
    #sidebar {{
        width: 32; background: {t['bg_dark']};
        border-right: solid {t['border']};
    }}
    #sidebar-title {{
        height: 1; padding: 0 2; color: {t['accent']};
        text-style: bold; background: {t['bg_dark']};
    }}
    #sidebar-rule {{
        height: 1; color: {t['border']}; background: {t['bg_dark']};
    }}
    #sidebar-count {{
        height: 1; padding: 0 2; color: {t['fg_dim']};
        background: {t['bg_dark']};
    }}
    #note-list {{
        height: 1fr; background: {t['bg_dark']};
        scrollbar-size: 1 1;
        scrollbar-color: {t['border']};
        scrollbar-color-hover: {t['accent']};
    }}
    NoteItem {{
        padding: 0 1; height: 3;
        border-bottom: solid {t['border']};
        background: {t['bg_dark']};
    }}
    NoteItem:hover {{ background: {t['bg_highlight']}; }}
    NoteItem.--highlight {{
        background: {t['bg_highlight']};
        border-left: tall {t['accent']};
    }}
    NoteItem.selected-item {{
        background: {t['red']} 15%;
        border-left: tall {t['red']};
    }}
    NoteItem.pinned-item .ni-title {{ color: {t['orange']}; }}

    .ni-title  {{ color: {t['fg']}; text-style: bold; height: 1; }}
    .ni-row    {{ height: 1; }}
    .ni-check  {{ width: 3; color: {t['red']}; text-style: bold; }}
    .ni-pin    {{ width: 3; color: {t['orange']}; }}
    .ni-date   {{ color: {t['yellow']}; width: 9; }}
    .ni-preview {{ color: {t['fg_dim']}; width: 1fr; overflow: hidden; }}

    /* ── Editor ── */
    #editor-pane {{ background: {t['bg']}; }}
    #statusbar   {{ height: 1; }}
    #status-left {{
        height: 1; background: {t['accent']}; color: {t['bg']};
        text-style: bold; width: 1fr; padding: 0 1;
    }}
    #status-right {{
        height: 1; background: {t['accent2']}; color: {t['bg']};
        text-style: bold; width: auto; padding: 0 1;
    }}
    #select-bar {{
        height: 1; background: {t['red']} 25%; color: {t['red']};
        text-style: bold; padding: 0 1; display: none;
    }}
    #select-bar.active {{ display: block; }}
    #sync-bar {{
        height: 1; background: {t['bg_dark']}; color: {t['fg_dim']};
        padding: 0 1;
    }}
    #editor {{
        height: 1fr; border: none;
        background: {t['bg']}; color: {t['fg']}; padding: 1 3;
    }}
    #editor:focus {{ border: none; }}
    .text-area--cursor    {{ background: {t['accent']};       color: {t['bg']}; }}
    .text-area--gutter    {{ background: {t['bg']};           color: {t['fg_dark']}; }}
    .text-area--selection {{ background: {t['bg_highlight']}; }}

    /* ── Modals ── */
    ConfirmDelete {{ align: center middle; }}
    ConfirmDeleteMulti {{ align: center middle; }}
    #dialog {{
        background: {t['bg_dark']}; border: solid {t['red']};
        padding: 2 4; width: 52; height: auto;
    }}
    #dialog-title {{
        text-style: bold; color: {t['red']}; margin-bottom: 1;
        content-align: center middle; width: 100%;
    }}
    #dialog-note {{
        color: {t['fg']}; margin-bottom: 2;
        content-align: center middle; width: 100%; text-style: italic;
    }}
    #dialog-hint {{
        color: {t['fg_dim']}; content-align: center middle; width: 100%;
    }}

    /* ── Help modal ── */
    HelpScreen {{ align: center middle; }}
    #help-box {{
        width: 58; height: auto; background: {t['bg_dark']};
        border: solid {t['accent']}; padding: 1 3;
    }}
    #help-title {{
        color: {t['accent']}; text-style: bold;
        content-align: center middle; width: 100%;
        border-bottom: solid {t['border']}; padding-bottom: 1; margin-bottom: 1;
    }}
    #help-close {{
        color: {t['fg_dark']}; content-align: center middle;
        width: 100%; margin-top: 1;
        border-top: solid {t['border']}; padding-top: 1;
    }}
    .help-section {{
        color: {t['accent2']}; text-style: bold; margin-top: 1;
    }}
    .help-row {{ height: 1; width: 100%; }}
    .help-key  {{ color: {t['accent']}; text-style: bold; width: 18; }}
    .help-desc {{ color: {t['fg_dim']}; width: 1fr; }}

    /* ── Footer ── */
    Footer {{
        background: {t['bg_dark']}; color: {t['fg_dim']};
        border-top: solid {t['border']};
    }}
    Footer > .footer--key       {{ color: {t['accent']};  background: {t['bg_dark']}; }}
    Footer > .footer--highlight {{ background: {t['bg_dark']}; color: {t['fg_dim']}; }}
    """


# ══════════════════════════════════════════════════════════════════════════════
#  Modals
# ══════════════════════════════════════════════════════════════════════════════

class ConfirmDelete(ModalScreen):
    CSS = make_css()
    BINDINGS = [
        Binding("y", "confirm", show=False),
        Binding("n", "cancel",  show=False),
        Binding("escape", "cancel", show=False),
    ]

    def __init__(self, title: str):
        super().__init__()
        self.note_title = title

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(" delete note?", id="dialog-title")
            yield Static(f'"{self.note_title}"', id="dialog-note")
            yield Static("[y] yes    [n] / [esc] no", id="dialog-hint")

    def on_mount(self) -> None:
        self.focus()

    def action_confirm(self): self.dismiss(True)
    def action_cancel(self):  self.dismiss(False)


class ConfirmDeleteMulti(ModalScreen):
    CSS = make_css()
    BINDINGS = [
        Binding("y", "confirm", show=False),
        Binding("n", "cancel",  show=False),
        Binding("escape", "cancel", show=False),
    ]

    def __init__(self, count: int):
        super().__init__()
        self.count = count

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(" delete selected notes?", id="dialog-title")
            yield Static(
                f"{self.count} {'note' if self.count == 1 else 'notes'} will be permanently deleted",
                id="dialog-note"
            )
            yield Static("[y] yes    [n] / [esc] no", id="dialog-hint")

    def on_mount(self) -> None:
        self.focus()

    def action_confirm(self): self.dismiss(True)
    def action_cancel(self):  self.dismiss(False)


# ══════════════════════════════════════════════════════════════════════════════
#  Help / keybind modal
# ══════════════════════════════════════════════════════════════════════════════

KEYBINDS = [
    ("NAVIGATION", [
        ("tab",           "switch sidebar / editor"),
        ("j / k",         "move up / down in list"),
        ("enter",         "open selected note"),
        ("escape",        "go back to home screen"),
    ]),
    ("NOTES", [
        ("ctrl+n",        "new note"),
        ("ctrl+d",        "delete current note"),
        ("p",             "pin / unpin note"),
        ("ctrl+p",        "pin / unpin (from editor)"),
    ]),
    ("MULTI-SELECT", [
        ("v",             "enter / exit select mode"),
        ("space",         "mark / unmark note"),
        ("ctrl+d",        "delete all selected notes"),
    ]),
    ("SYNC", [
        ("ctrl+u",        "force push to github"),
    ]),
    ("APP", [
        ("?",             "show this help screen"),
        ("ctrl+q",        "quit"),
    ]),
]


class HelpScreen(ModalScreen):
    CSS = make_css()
    BINDINGS = [
        Binding("escape", "close", show=False),
        Binding("q",      "close", show=False),
        Binding("?",      "close", show=False),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="help-box"):
            yield Static(" keybindings", id="help-title")
            for section, binds in KEYBINDS:
                yield Static(f" {section}", classes="help-section")
                for key, desc in binds:
                    with Horizontal(classes="help-row"):
                        yield Static(f" {key}", classes="help-key")
                        yield Static(desc, classes="help-desc")
            yield Static("esc / q / ?  close", id="help-close")

    def on_mount(self) -> None:
        self.focus()

    def action_close(self) -> None:
        self.dismiss()


# ══════════════════════════════════════════════════════════════════════════════
#  Setup screen
# ══════════════════════════════════════════════════════════════════════════════

class SetupScreen(Screen):
    CSS = make_css()
    BINDINGS = [Binding("escape", "skip", show=False)]

    def compose(self) -> ComposeResult:
        with Middle():
            with Center():
                with Vertical(id="setup-box"):
                    yield Static(LOGO, id="logo")
                    yield Static(" github sync setup", id="setup-title")
                    yield Static(
                        "token stored in ~/.local/share/notes-tui/config.json (chmod 600)",
                        id="setup-sub"
                    )
                    yield Static(" github personal access token (repo scope):", classes="setup-label")
                    yield Input(placeholder="ghp_...", password=True, id="input-token", classes="setup-input")
                    yield Static(" github username:", classes="setup-label")
                    yield Input(placeholder="nebula762814", id="input-user", classes="setup-input")
                    yield Static(" repo name (created if missing):", classes="setup-label")
                    yield Input(placeholder="my-notes", id="input-repo", classes="setup-input")
                    yield Static("", id="setup-status")
                    yield Static("enter  next field / save   esc  skip", id="setup-hint")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        inputs = ["input-token", "input-user", "input-repo"]
        idx = inputs.index(event.input.id)
        if idx < len(inputs) - 1:
            self.query_one(f"#{inputs[idx + 1]}", Input).focus()
        else:
            self._save()

    def _save(self) -> None:
        token  = self.query_one("#input-token", Input).value.strip()
        user   = self.query_one("#input-user",  Input).value.strip()
        repo   = self.query_one("#input-repo",  Input).value.strip()
        status = self.query_one("#setup-status", Static)
        if not token or not user or not repo:
            status.update(" all fields required")
            return
        status.update(" checking...")
        self.set_timer(0.05, lambda: self._do_save(token, user, repo))

    def _do_save(self, token: str, user: str, repo: str) -> None:
        status = self.query_one("#setup-status", Static)
        ok, msg = GitHubSync.ensure_repo_exists(token, user, repo)
        if not ok:
            status.update(f" error: {msg}")
            return
        save_config({"token": token, "username": user, "repo": repo})
        action = "created" if msg == "created" else "found"
        status.update(f" repo {action}! config saved.")
        self.set_timer(0.8, self.app.pop_screen)

    def action_skip(self) -> None:
        self.app.pop_screen()


# ══════════════════════════════════════════════════════════════════════════════
#  Note list item
# ══════════════════════════════════════════════════════════════════════════════

class NoteItem(ListItem):
    def __init__(self, note: dict, selected: bool = False) -> None:
        super().__init__()
        self.note_id  = note["id"]
        self._note    = note
        self._selected = selected
        self._pinned   = note.get("pinned", False)

    def compose(self) -> ComposeResult:
        title   = self._note.get("title") or "Untitled"
        preview = (self._note.get("body") or "").replace("\n", " ")[:28]
        date    = fmt_date(self._note.get("modified", self._note.get("created", "")))
        pin_sym = "󰐃 " if self._pinned else "  "
        chk_sym = "✓ " if self._selected else "  "
        yield Label(title, classes="ni-title")
        with Horizontal(classes="ni-row"):
            yield Label(chk_sym, classes="ni-check")
            yield Label(pin_sym, classes="ni-pin")
            yield Label(date,    classes="ni-date")
            yield Label(preview or "~", classes="ni-preview")

    def on_mount(self) -> None:
        self._apply_classes()

    def _apply_classes(self) -> None:
        classes = set()
        if self._selected: classes.add("selected-item")
        if self._pinned:   classes.add("pinned-item")
        self.set_classes(" ".join(classes) if classes else "")

    def set_selected(self, val: bool) -> None:
        self._selected = val
        try:
            self.query_one(".ni-check", Label).update("✓ " if val else "  ")
        except Exception:
            pass
        self._apply_classes()

    def set_pinned(self, val: bool) -> None:
        self._pinned = val
        try:
            self.query_one(".ni-pin", Label).update("󰐃 " if val else "  ")
        except Exception:
            pass
        self._apply_classes()


# ══════════════════════════════════════════════════════════════════════════════
#  Splash screen
# ══════════════════════════════════════════════════════════════════════════════

MENU = [
    ("n", " new note",     "open_new"),
    ("b", " browse notes", "open_browse"),
    ("r", " recent note",  "open_recent"),
    ("s", " sync setup",   "open_setup"),
    ("q", " quit",         "do_quit"),
]


class SplashScreen(Screen):
    CSS = make_css()
    BINDINGS = [
        Binding("j",     "move_down",  show=False),
        Binding("k",     "move_up",    show=False),
        Binding("down",  "move_down",  show=False),
        Binding("up",    "move_up",    show=False),
        Binding("enter", "select",     show=False),
        Binding("n",     "sc_0",       show=False),
        Binding("b",     "sc_1",       show=False),
        Binding("r",     "sc_2",       show=False),
        Binding("s",     "sc_3",       show=False),
        Binding("q",     "sc_4",       show=False),
    ]

    cursor: reactive[int] = reactive(0)

    def compose(self) -> ComposeResult:
        cfg   = load_config()
        notes = load_notes()
        count = len(notes)
        sync_status = " (sync on)" if cfg.get("token") else " (no sync — s to setup)"
        with Middle():
            with Center():
                yield Static(LOGO, id="logo")
                yield Static("plain-text note taking, nvim style", id="tagline")
                with Vertical(id="menu-wrap"):
                    for i, (key, label, _) in enumerate(MENU):
                        cls = "menu-selected" if i == 0 else "menu-item"
                        yield Static(f" [{key}]  {label}", id=f"mi-{i}", classes=cls)
                yield Static("j/k  navigate   enter  select   letter  shortcut", id="splash-hint")
                yield Static(
                    f"notes v2.0   {count} {'note' if count == 1 else 'notes'}{sync_status}",
                    id="splash-version"
                )

    def watch_cursor(self, old: int, new: int) -> None:
        try:
            self.query_one(f"#mi-{old}", Static).set_classes("menu-item")
            self.query_one(f"#mi-{new}", Static).set_classes("menu-selected")
        except Exception:
            pass

    def action_move_down(self): self.cursor = (self.cursor + 1) % len(MENU)
    def action_move_up(self):   self.cursor = (self.cursor - 1) % len(MENU)
    def action_select(self):    getattr(self, MENU[self.cursor][2])()
    def action_sc_0(self): self.open_new()
    def action_sc_1(self): self.open_browse()
    def action_sc_2(self): self.open_recent()
    def action_sc_3(self): self.open_setup()
    def action_sc_4(self): self.do_quit()

    def open_new(self):    self.app.push_screen(MainScreen(open_new=True))
    def open_browse(self): self.app.push_screen(MainScreen())
    def open_recent(self):
        notes = load_notes()
        self.app.push_screen(MainScreen(focus_idx=0 if notes else -1))
    def open_setup(self):  self.app.push_screen(SetupScreen())
    def do_quit(self):     self.app.exit()


# ══════════════════════════════════════════════════════════════════════════════
#  Main screen
# ══════════════════════════════════════════════════════════════════════════════

class MainScreen(Screen):
    CSS = make_css()

    # Normal mode bindings
    BINDINGS = [
        Binding("ctrl+n", "new_note",      "New"),
        Binding("ctrl+d", "delete_note",   "Delete"),
        Binding("ctrl+p", "pin_note",      "Pin"),
        Binding("v",      "toggle_select", "Select", show=True),
        Binding("ctrl+u", "push_sync",     "Sync↑"),
        Binding("?",      "show_help",     "Help"),
        Binding("escape", "go_home",       "Home"),
        Binding("tab",    "swap_focus",    "Switch", show=False),
        Binding("ctrl+q", "do_quit",       "Quit"),
    ]

    _saving:       bool       = False
    _select_mode:  bool       = False
    _selected_ids: set[str]   = set()

    def __init__(self, open_new: bool = False, focus_idx: int = 0):
        super().__init__()
        self._selected_ids = set()
        raw = load_notes()
        self.notes: list[dict] = sorted_notes(raw)
        self.sel: int = (
            max(0, min(focus_idx, len(self.notes) - 1))
            if self.notes else -1
        )
        self._open_new = open_new
        cfg = load_config()
        self._sync: GitHubSync | None = (
            GitHubSync(cfg["token"], cfg["username"], cfg["repo"])
            if cfg.get("token") else None
        )

    # ── Layout ────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical(id="sidebar"):
                yield Static(" NOTES", id="sidebar-title")
                yield Static("─" * 30, id="sidebar-rule")
                yield Static("", id="sidebar-count")
                yield ListView(id="note-list")
            with Vertical(id="editor-pane"):
                with Horizontal(id="statusbar"):
                    yield Static("  NORMAL", id="status-left")
                    yield Static("", id="status-right")
                yield Static("", id="select-bar")
                yield Static("", id="sync-bar")
                yield TextArea("", id="editor", show_line_numbers=True)
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_list()
        if self._open_new:
            self.action_new_note()
        elif self.notes and self.sel >= 0:
            self._load_note(self.sel)
        if self._sync:
            self._set_sync_bar(" pulling from github...")
            threading.Thread(target=self._bg_pull, daemon=True).start()

    # ── GitHub ────────────────────────────────────────────────────────────────

    def _bg_pull(self) -> None:
        notes, msg = self._sync.pull()
        if notes is not None:
            remote_ids  = {n["id"] for n in notes}
            local_only  = [n for n in self.notes if n["id"] not in remote_ids]
            self.notes  = sorted_notes(notes + local_only)
            save_notes(self.notes)
            self.call_from_thread(self._after_pull)
        else:
            self.call_from_thread(self._set_sync_bar, f" pull failed: {msg}")

    def _after_pull(self) -> None:
        self._refresh_list()
        if self.notes and self.sel < 0:
            self.sel = 0
            self._load_note(0)
        self._set_sync_bar(" synced with github")
        self.set_timer(3, lambda: self._set_sync_bar(""))

    def _bg_push(self) -> None:
        ok, msg = self._sync.push(self.notes)
        self.call_from_thread(
            self._set_sync_bar,
            " pushed to github" if ok else f" push failed: {msg}"
        )
        self.call_from_thread(self.set_timer, 3, lambda: self._set_sync_bar(""))

    def _trigger_push(self) -> None:
        if not self._sync:
            return
        if hasattr(self, "_sync_timer"):
            try: self._sync_timer.cancel()
            except Exception: pass
        self._sync_timer = threading.Timer(
            2.0, lambda: threading.Thread(target=self._bg_push, daemon=True).start()
        )
        self._sync_timer.start()

    def _set_sync_bar(self, msg: str) -> None:
        try: self.query_one("#sync-bar", Static).update(msg)
        except Exception: pass

    # ── List helpers ──────────────────────────────────────────────────────────

    def _refresh_list(self) -> None:
        lv = self.query_one("#note-list", ListView)
        lv.clear()
        for note in self.notes:
            lv.append(NoteItem(note, selected=note["id"] in self._selected_ids))
        n = len(self.notes)
        self.query_one("#sidebar-count", Static).update(
            f"  {n} {'note' if n == 1 else 'notes'}"
        )
        if self.notes:
            lv.index = max(0, min(self.sel, n - 1))

    def _load_note(self, idx: int) -> None:
        if not self.notes or idx < 0 or idx >= len(self.notes):
            self._set_status("  NORMAL", "")
            self.query_one("#editor", TextArea).load_text("")
            return
        note = self.notes[idx]
        self.sel = idx
        pin_tag = " 󰐃" if note.get("pinned") else ""
        content = (note.get("title") or "") + "\n\n" + (note.get("body") or "")
        self._saving = True
        self.query_one("#editor", TextArea).load_text(content)
        self._saving = False
        self._set_status(
            f"  NORMAL{pin_tag}   {note.get('title') or 'Untitled'}",
            f" modified {fmt_date(note.get('modified', ''))} "
        )

    def _set_status(self, left: str, right: str) -> None:
        try:
            self.query_one("#status-left",  Static).update(left)
            self.query_one("#status-right", Static).update(right)
        except Exception: pass

    def _update_select_bar(self) -> None:
        bar = self.query_one("#select-bar", Static)
        if self._select_mode:
            n = len(self._selected_ids)
            bar.update(
                f" SELECT  {n} selected   space mark/unmark   ctrl+d delete   v exit select"
            )
            bar.add_class("active")
        else:
            bar.update("")
            bar.remove_class("active")

    def _refresh_item(self, idx: int) -> None:
        items = list(self.query_one("#note-list", ListView).query(NoteItem))
        if 0 <= idx < len(items) and idx < len(self.notes):
            n = self.notes[idx]
            try:
                items[idx]._note = n
                items[idx].query_one(".ni-title",   Label).update(n.get("title") or "Untitled")
                items[idx].query_one(".ni-date",    Label).update(fmt_date(n.get("modified", "")))
                items[idx].query_one(".ni-preview", Label).update(
                    (n.get("body") or "").replace("\n", " ")[:28] or "~"
                )
                items[idx].set_pinned(n.get("pinned", False))
            except Exception: pass

    # ── Events ────────────────────────────────────────────────────────────────

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if not isinstance(event.item, NoteItem):
            return
        note_id = event.item.note_id
        if self._select_mode:
            # Space/enter in select mode toggles selection
            self._toggle_selection(note_id, event.item)
            return
        for i, n in enumerate(self.notes):
            if n["id"] == note_id:
                self._load_note(i)
                self.query_one("#editor", TextArea).focus()
                break

    def on_key(self, event) -> None:
        """Handle space for marking items while list is focused."""
        lv = self.query_one("#note-list", ListView)
        if event.key == "space" and self._select_mode and not self.query_one("#editor", TextArea).has_focus:
            event.stop()
            items = list(lv.query(NoteItem))
            idx   = lv.index
            if idx is not None and 0 <= idx < len(items):
                note_id = items[idx].note_id
                self._toggle_selection(note_id, items[idx])
            return
        if event.key == "p" and not self.query_one("#editor", TextArea).has_focus:
            event.stop()
            self.action_pin_note()

    def _toggle_selection(self, note_id: str, item: NoteItem) -> None:
        if note_id in self._selected_ids:
            self._selected_ids.discard(note_id)
            item.set_selected(False)
        else:
            self._selected_ids.add(note_id)
            item.set_selected(True)
        self._update_select_bar()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if self._saving or self.sel < 0 or self.sel >= len(self.notes):
            return
        lines = event.text_area.text.split("\n")
        title = lines[0].strip() or "Untitled"
        body  = "\n".join(lines[2:]) if len(lines) > 2 else ""
        note  = self.notes[self.sel]
        note["title"]    = title
        note["body"]     = body
        note["modified"] = datetime.now().isoformat(timespec="seconds")
        save_notes(self.notes)
        self._refresh_item(self.sel)
        pin_tag = " 󰐃" if note.get("pinned") else ""
        self._set_status(
            f"  INSERT{pin_tag}   {title}",
            f" modified {fmt_date(note['modified'])} "
        )
        self._trigger_push()

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_new_note(self) -> None:
        note = new_note()
        self.notes.insert(0, note)
        # pinned notes still float, re-sort
        self.notes = sorted_notes(self.notes)
        save_notes(self.notes)
        self.sel = next(i for i, n in enumerate(self.notes) if n["id"] == note["id"])
        self._refresh_list()
        self._load_note(self.sel)
        ed = self.query_one("#editor", TextArea)
        ed.focus()
        ed.move_cursor((0, 0))
        self._set_status("  INSERT   Untitled", " new note ")

    def action_toggle_select(self) -> None:
        self._select_mode = not self._select_mode
        if not self._select_mode:
            self._selected_ids.clear()
            self._refresh_list()
        self._update_select_bar()
        if self._select_mode:
            self.query_one("#note-list", ListView).focus()

    def action_delete_note(self) -> None:
        if not self.notes:
            return
        # Multi-select delete
        if self._select_mode and self._selected_ids:
            count = len(self._selected_ids)
            self.app.push_screen(ConfirmDeleteMulti(count), self._confirmed_delete_multi)
            return
        # Single delete
        if self.sel < 0:
            return
        title = self.notes[self.sel].get("title") or "Untitled"
        self.app.push_screen(ConfirmDelete(title), self._confirmed_delete_single)

    def _confirmed_delete_single(self, yes: bool) -> None:
        if not yes:
            return
        self.notes.pop(self.sel)
        save_notes(self.notes)
        self.sel = min(self.sel, len(self.notes) - 1)
        self._refresh_list()
        if self.notes:
            self._load_note(self.sel)
        else:
            self.query_one("#editor", TextArea).load_text("")
            self._set_status("  NORMAL", "")
        if self._sync:
            threading.Thread(target=self._bg_push, daemon=True).start()

    def _confirmed_delete_multi(self, yes: bool) -> None:
        if not yes:
            return
        self.notes = [n for n in self.notes if n["id"] not in self._selected_ids]
        save_notes(self.notes)
        self._selected_ids.clear()
        self._select_mode = False
        self._update_select_bar()
        self.sel = 0 if self.notes else -1
        self._refresh_list()
        if self.notes:
            self._load_note(self.sel)
        else:
            self.query_one("#editor", TextArea).load_text("")
            self._set_status("  NORMAL", "")
        if self._sync:
            threading.Thread(target=self._bg_push, daemon=True).start()

    def action_pin_note(self) -> None:
        if not self.notes or self.sel < 0:
            return
        note = self.notes[self.sel]
        note["pinned"] = not note.get("pinned", False)
        save_notes(self.notes)
        # Re-sort so pinned notes float up
        current_id = note["id"]
        self.notes = sorted_notes(self.notes)
        self.sel = next(i for i, n in enumerate(self.notes) if n["id"] == current_id)
        self._refresh_list()
        self._load_note(self.sel)
        self._trigger_push()

    def action_push_sync(self) -> None:
        if not self._sync:
            self._set_sync_bar(" no sync configured — press s on home screen")
            self.set_timer(3, lambda: self._set_sync_bar(""))
            return
        self._set_sync_bar(" pushing to github...")
        threading.Thread(target=self._bg_push, daemon=True).start()

    def action_go_home(self)    -> None: self.app.pop_screen()
    def action_do_quit(self)    -> None: self.app.exit()
    def action_show_help(self)  -> None: self.app.push_screen(HelpScreen())
    def action_swap_focus(self) -> None:
        ed = self.query_one("#editor", TextArea)
        lv = self.query_one("#note-list", ListView)
        lv.focus() if ed.has_focus else ed.focus()


# ══════════════════════════════════════════════════════════════════════════════
#  App
# ══════════════════════════════════════════════════════════════════════════════

class NotesApp(App):
    CSS = make_css()

    def on_mount(self) -> None:
        if not load_config().get("token"):
            self.push_screen(SplashScreen())
            self.push_screen(SetupScreen())
        else:
            self.push_screen(SplashScreen())


def main():
    NotesApp().run()

if __name__ == "__main__":
    main()
