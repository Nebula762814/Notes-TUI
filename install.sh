#!/usr/bin/env bash
# install.sh — sets up the `notes` TUI command
set -e

INSTALL_DIR="$HOME/.local/share/notes-tui"
BIN_DIR="$HOME/.local/bin"

echo "Installing notes TUI..."

# 1. Copy app
mkdir -p "$INSTALL_DIR"
cp notes.py "$INSTALL_DIR/notes.py"
chmod +x "$INSTALL_DIR/notes.py"

# 2. Check/install textual
if ! python3 -c "import textual" 2>/dev/null; then
    echo "Installing textual..."
    pip3 install textual --break-system-packages -q
fi

# 3. Create launcher
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/notes" << 'EOF'
#!/usr/bin/env bash
exec python3 "$HOME/.local/share/notes-tui/notes.py" "$@"
EOF
chmod +x "$BIN_DIR/notes"

# 4. PATH hint
if ! echo "$PATH" | grep -q "$HOME/.local/bin"; then
    echo ""
    echo "  Add this to your ~/.bashrc or ~/.zshrc (or ~/.zprofile on Arch):"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo ""
    echo "  Then run: source ~/.zshrc   (or your shell's rc file)"
fi

echo "Done! Type 'notes' to launch."
