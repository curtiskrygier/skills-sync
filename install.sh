#!/usr/bin/env bash
# install.sh — Bootstrap skills-sync on a new machine.
#
# Installs to ~/.local/share/sync-skills/ and symlinks skills into
# both Gemini CLI (~/.gemini/skills) and Claude Code (~/.claude/skills).
#
# No gcloud required. Two ways to provide credentials:
#
# 1. Place your SA key .json in the same folder as install.sh and run:
#      bash install.sh
#    The script detects the key and prompts for anything else it needs.
#
# 2. Pass everything via heredoc (useful from a password manager):
#      bash install.sh << 'EOF'
#      DRIVE_ID=YOUR_SHARED_DRIVE_ID
#      SA_NAME=YOUR_SA_KEY_FILENAME.json
#      SA_KEY_B64=YOUR_BASE64_ENCODED_SA_KEY
#      DRIVE_FOLDER=skills   # optional subfolder within the Shared Drive
#      EOF
#
# To generate SA_KEY_B64 from your key file:
#   Linux:  base64 -w 0 path/to/your-sa-key.json
#   macOS:  base64 path/to/your-sa-key.json
#
# To find your DRIVE_ID: open the Shared Drive in your browser.
# The URL will look like: drive.google.com/drive/folders/THIS_IS_YOUR_DRIVE_ID

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# macOS uses -D, Linux uses -d
[[ "$(uname)" == "Darwin" ]] && BASE64_DECODE="base64 -D" || BASE64_DECODE="base64 -d"

# ── Fixed install paths ───────────────────────────────────────────────────────
SYNC_DIR="${HOME}/.local/share/sync-skills"
SKILLS_DIR="${SYNC_DIR}/skills"
VENV_DIR="${SYNC_DIR}/venv"

# ── Parse stdin (heredoc / pipe mode) ────────────────────────────────────────
DRIVE_ID=""
SA_NAME=""
SA_KEY_B64=""
SA_KEY_FILE=""
DRIVE_FOLDER=""

current_key=""
if [[ ! -t 0 ]]; then
    while IFS= read -r line || [[ -n "${line:-}" ]]; do
        [[ -z "${line:-}" || "${line}" == \#* ]] && continue
        trimmed="${line#"${line%%[![:space:]]*}"}"  # trim leading whitespace

        if [[ "$trimmed" == *=* ]]; then
            key="${trimmed%%=*}"
            val="${trimmed#*=}"
            current_key="$key"
            case "$key" in
                DRIVE_ID)     DRIVE_ID="$val" ;;
                SA_NAME)      SA_NAME="$val" ;;
                SA_KEY_B64)   SA_KEY_B64="$val" ;;
                DRIVE_FOLDER) DRIVE_FOLDER="$val" ;;
            esac
        else
            # continuation line — append to current key (handles wrapped base64)
            case "$current_key" in
                SA_KEY_B64)  SA_KEY_B64="${SA_KEY_B64}${trimmed}" ;;
            esac
        fi
    done
fi

# ── Auto-detect SA key JSON if not provided via heredoc ──────────────────────
if [[ -z "$SA_KEY_B64" ]]; then
    found_keys=()
    while IFS= read -r f; do
        found_keys+=("$f")
    done < <(find "$SCRIPT_DIR" -maxdepth 1 -name "*.json" 2>/dev/null)

    if [[ ${#found_keys[@]} -eq 1 ]]; then
        SA_KEY_FILE="${found_keys[0]}"
        [[ -z "$SA_NAME" ]] && SA_NAME="$(basename "$SA_KEY_FILE")"
        echo "Found SA key: $SA_NAME"
    elif [[ ${#found_keys[@]} -gt 1 ]]; then
        echo "ERROR: Multiple JSON files found in $SCRIPT_DIR"
        echo "Remove all but your SA key file, or specify SA_NAME= in your heredoc input."
        exit 1
    fi
fi

# ── Interactive prompts for anything still missing ────────────────────────────
if [[ -z "$DRIVE_ID" ]]; then
    read -rp "Shared Drive ID (from the Drive URL): " DRIVE_ID
fi

if [[ -z "$SA_KEY_B64" && -z "$SA_KEY_FILE" ]]; then
    echo ""
    echo "No SA key found. Either:"
    echo "  • Place your .json key file in the same directory as install.sh, or"
    echo "  • Provide SA_KEY_B64=<base64-encoded key> in a heredoc"
    echo ""
    echo "  To encode your key:"
    echo "    Linux: base64 -w 0 your-sa-key.json"
    echo "    macOS: base64 your-sa-key.json"
    exit 1
fi

if [[ -z "$SA_NAME" ]]; then
    read -rp "SA key filename (e.g. my-project-abc123.json): " SA_NAME
fi

# ── Validate ──────────────────────────────────────────────────────────────────
if [[ -z "$DRIVE_ID" ]]; then
    echo "ERROR: DRIVE_ID is required."
    exit 1
fi

if [[ "$DRIVE_ID" =~ ^https?:// ]]; then
    echo "ERROR: DRIVE_ID looks like a URL. Paste just the ID from the end of the URL."
    echo "  e.g. from https://drive.google.com/drive/folders/0AALIUj_e6cRVUk9PVA"
    echo "  use:  0AALIUj_e6cRVUk9PVA"
    exit 1
fi

echo ""
echo "=== skills-sync bootstrap ==="
echo "Install: $SYNC_DIR"
echo "Skills:  $SKILLS_DIR"
echo "Venv:    $VENV_DIR"
[[ -n "$DRIVE_FOLDER" ]] && echo "Drive folder: $DRIVE_FOLDER"
echo ""

# ── Create directory structure ────────────────────────────────────────────────
mkdir -p "$SYNC_DIR"
chmod 700 "$SYNC_DIR"
mkdir -p "$SKILLS_DIR"

# ── Write SA key ──────────────────────────────────────────────────────────────
if [[ -n "$SA_KEY_FILE" ]]; then
    cp "$SA_KEY_FILE" "$SYNC_DIR/$SA_NAME"
else
    echo "$SA_KEY_B64" | $BASE64_DECODE > "$SYNC_DIR/$SA_NAME"
fi
chmod 600 "$SYNC_DIR/$SA_NAME"
echo "SA key written and secured: $SYNC_DIR/$SA_NAME"
printf '*.json\n.last_sync\n' > "$SYNC_DIR/.gitignore"

# ── Persist config ────────────────────────────────────────────────────────────
cat > "$SYNC_DIR/.config" << CONF
SHARED_DRIVE_ID=$DRIVE_ID
DRIVE_FOLDER=$DRIVE_FOLDER
CONF
chmod 600 "$SYNC_DIR/.config"
echo "Config written: $SYNC_DIR/.config"

# ── Python venv ───────────────────────────────────────────────────────────────
if [[ ! -f "$VENV_DIR/bin/python" ]]; then
    echo "Creating Python venv..."
    python3 -m venv "$VENV_DIR"
fi
echo "Installing dependencies..."
if ! "$VENV_DIR/bin/pip" install --require-hashes -r "$SCRIPT_DIR/requirements.lock" --quiet; then
    echo "ERROR: dependency install failed. Check Python version (3.8+ required) and network access."
    exit 1
fi
echo "Dependencies ready."

# ── D2 diagramming tool ───────────────────────────────────────────────────────
if command -v d2 &>/dev/null; then
    echo "D2 already installed: $(d2 --version)"
else
    echo "Installing D2 diagramming tool..."
    if command -v curl &>/dev/null; then
        curl -fsSL https://d2lang.com/install.sh | sh -s -- --quiet
        if command -v d2 &>/dev/null; then
            echo "D2 installed: $(d2 --version)"
        else
            echo "Warning: D2 install may need PATH reload. Run: source ~/.bashrc (or ~/.zshrc)"
            echo "  Or install manually: https://github.com/terrastruct/d2/releases"
        fi
    else
        echo "Warning: curl not found — install D2 manually: https://github.com/terrastruct/d2/releases"
    fi
fi

# ── Copy sync_skills.py ───────────────────────────────────────────────────────
SYNC_SCRIPT="$SYNC_DIR/sync_skills.py"
cp "$SCRIPT_DIR/sync_skills.py" "$SYNC_SCRIPT"
echo "sync_skills.py installed."

# ── Wrapper command ───────────────────────────────────────────────────────────
mkdir -p "${HOME}/.local/bin"
cat > "${HOME}/.local/bin/skills-sync" << WRAPPER
#!/usr/bin/env bash
exec "$VENV_DIR/bin/python" "$SYNC_SCRIPT" "\$@"
WRAPPER
chmod +x "${HOME}/.local/bin/skills-sync"
echo "Wrapper installed: ~/.local/bin/skills-sync"
if [[ ":$PATH:" != *":${HOME}/.local/bin:"* ]]; then
    echo "  Note: add ~/.local/bin to your PATH to use 'skills-sync' directly."
fi

# ── Seed example skill ────────────────────────────────────────────────────────
if [[ -d "$SCRIPT_DIR/skills/example" && ! -d "$SKILLS_DIR/example" ]]; then
    cp -r "$SCRIPT_DIR/skills/example" "$SKILLS_DIR/example"
    echo "Example skill created: $SKILLS_DIR/example/SKILL.md"
fi

# ── Pull all skills from Drive ────────────────────────────────────────────────
echo "Pulling skills from Drive..."
SHARED_DRIVE_ID="$DRIVE_ID" DRIVE_FOLDER="$DRIVE_FOLDER" "$VENV_DIR/bin/python" "$SYNC_SCRIPT" --pull

# ── Gemini CLI skills symlink ─────────────────────────────────────────────────
mkdir -p "${HOME}/.gemini"
if [[ -d "${HOME}/.gemini/skills" && ! -L "${HOME}/.gemini/skills" ]]; then
    echo "Warning: ~/.gemini/skills is a real directory — renaming to ~/.gemini/skills.bak"
    mv "${HOME}/.gemini/skills" "${HOME}/.gemini/skills.bak"
fi
ln -sfn "$SKILLS_DIR" "${HOME}/.gemini/skills"
echo "Gemini CLI: skills linked → ~/.gemini/skills"

# ── Claude Code skills symlink ────────────────────────────────────────────────
mkdir -p "${HOME}/.claude"
if [[ -d "${HOME}/.claude/skills" && ! -L "${HOME}/.claude/skills" ]]; then
    echo "Warning: ~/.claude/skills is a real directory — renaming to ~/.claude/skills.bak"
    mv "${HOME}/.claude/skills" "${HOME}/.claude/skills.bak"
fi
ln -sfn "$SKILLS_DIR" "${HOME}/.claude/skills"
echo "Claude Code: skills linked → ~/.claude/skills"

# ── Claude Code global config ─────────────────────────────────────────────────
CLAUDE_MD="${HOME}/.claude/CLAUDE.md"
python3 - <<PYEOF
import re, pathlib
p = pathlib.Path("$CLAUDE_MD")
content = p.read_text() if p.exists() else ""
section = "## Skills Library\nSkills are in $SKILLS_DIR — read SKILL.md files from subdirectories when relevant."
pattern = r'## Skills Library\n[^\n]*'
if re.search(pattern, content):
    content = re.sub(pattern, lambda m: section, content)
    print("Claude Code: updated existing Skills Library entry in ~/.claude/CLAUDE.md")
else:
    content = content.rstrip('\n') + ('\n\n' if content else '') + section + '\n'
    print("Claude Code: added Skills Library entry to ~/.claude/CLAUDE.md")
p.write_text(content)
PYEOF

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "=== Bootstrap complete ==="
echo ""
echo "  Skills:       $SKILLS_DIR"
echo "  Sync script:  $SYNC_SCRIPT"
echo "  SA key:       $SYNC_DIR/$SA_NAME"
echo "  Venv:         $VENV_DIR"
echo "  Gemini CLI:   ~/.gemini/skills → $SKILLS_DIR"
echo "  Claude Code:  ~/.claude/skills → $SKILLS_DIR"
echo ""
echo "To push changes:  skills-sync"
echo "To pull updates:  skills-sync --pull"
echo "To preview push:  skills-sync --dry-run"
