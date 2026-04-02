# Notes TUI

A fast, keyboard-driven terminal note-taking app inspired by Neovim.

Built with Python and Textual, this app lets you create, edit, and organize notes entirely from the terminal, with optional GitHub sync.

---

## Features

- Create and edit notes in a TUI
- Pin important notes
- Multi-select and delete notes
- Keyboard-first workflow (vim-style navigation)
- Optional GitHub sync
- Customizable theme

---

## Installation

### Option 1: Homebrew (Recommended)

brew tap Nebula762814/tap

brew install notes-tui

---

### Option 2: Manual Installation

git clone https://github.com/Nebula762814/Notes-TUI.git

cd Notes-TUI

chmod +x install.sh

./install.sh

---

## Usage

After installation:

notes

---

## Requirements

- Python 3.8+
- pip
- Internet connection (for GitHub sync)

The installer will automatically install required dependencies like textual.

---

## GitHub Sync Setup (Optional)

On first launch, you can enable GitHub sync.

You will need:
- A GitHub Personal Access Token (with repo scope)
- Your GitHub username
- A repository name (will be created automatically if it doesn’t exist)

Your notes will sync to a private repository as notes.json.

---

## Keybindings

Navigation:

j / k — Move up / down
Enter — Open note
Tab — Switch between list and editor
Esc — Back to menu

Notes:

Ctrl + N — New note
Ctrl + D — Delete note
P — Pin / unpin note

Multi-select:

V — Toggle select mode
Space — Select note
Ctrl + D — Delete selected

Sync:

Ctrl + U — Push to GitHub

App:

? — Help menu
Ctrl + Q — Quit

---

## Data Storage

Notes and config are stored locally at:

~/.local/share/notes-tui/

---

## Security Note

Your GitHub token is stored locally in:

~/.local/share/notes-tui/config.json

Permissions are set to restrict access (chmod 600), but keep your system secure and do not share this file.

---

## Contributing

Pull requests are welcome. Feel free to open issues for bugs or feature requests.

---

## License

MIT License

---

## Inspiration

Inspired by terminal-first workflows and tools like Neovim.
