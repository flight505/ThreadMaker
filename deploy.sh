#!/bin/bash
# Deploy ThreadMaker add-in to Fusion 360

ADDIN_DIR="$HOME/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/ThreadMaker"

echo "Deploying ThreadMaker to: $ADDIN_DIR"

# Remove old deployment
rm -rf "$ADDIN_DIR"

# Copy everything except git, .claude, .vscode
mkdir -p "$ADDIN_DIR"
rsync -av --exclude='.git' --exclude='.claude' --exclude='.vscode' --exclude='.gitignore' \
    --exclude='PLAN.md' --exclude='CLAUDE.md' --exclude='deploy.sh' --exclude='ScriptIcon.svg' \
    "$(dirname "$0")/" "$ADDIN_DIR/"

echo "Done. Restart the add-in in Fusion 360."
