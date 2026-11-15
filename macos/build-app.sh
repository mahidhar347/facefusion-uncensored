#!/bin/bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
app="$root/FaceFusion.app"

if [ -e "$app" ]; then
    echo "Move the existing $app before building a new copy." >&2
    exit 1
fi

scratch="$(mktemp -d "$root/.facefusion-build.XXXXXX")"
trap 'rm -rf "$scratch"' EXIT
contents="$scratch/FaceFusion.app/Contents"
mkdir -p "$contents/MacOS"
cp "$root/macos/Info.plist" "$contents/Info.plist"
swiftc "$root/macos/FaceFusionLauncher.swift" -o "$contents/MacOS/FaceFusion"
codesign --force --sign - "$scratch/FaceFusion.app"
mv "$scratch/FaceFusion.app" "$app"
printf 'Built %s\n' "$app"
