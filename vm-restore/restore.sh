#!/usr/bin/env bash
# Run on the replacement VM. The default only prints the restoration plan.
set -euo pipefail
export LC_ALL=C
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
apply=false
list="$ROOT/apt-packages.txt"
for arg in "$@"; do
    case "$arg" in
        --apply) apply=true ;;
        --manual-apt) list="$ROOT/apt-manual.txt" ;;
        --help|-h)
            echo "Usage: bash vm-restore/restore.sh [--apply] [--manual-apt]"
            echo "Default: preview all saved apt and Snap packages. --apply installs them."
            exit 0 ;;
        *) echo "Unknown option: $arg" >&2; exit 2 ;;
    esac
done

echo "APT manifest: $list ($(wc -l < "$list") packages)"
echo "Snap manifest: $ROOT/snap-packages.tsv"
if ! "$apply"; then
    echo "Preview only. No packages or system configuration will be changed."
    echo "With --apply: require Ubuntu 24.04 amd64; restore external apt sources and"
    echo "public keys, install apt packages and bundled onvifsim, then install Snaps."
    echo "Package versions follow current repositories; unavailable packages are reported."
    cat "$list"
    cat "$ROOT/snap-packages.tsv"
    exit 0
fi

source /etc/os-release
if [[ "$ID" != ubuntu || "$VERSION_ID" != 24.04 || $(dpkg --print-architecture) != amd64 ]]; then
    echo "This snapshot requires Ubuntu 24.04 amd64. See README.vi.md." >&2
    exit 1
fi
sudo -v
while IFS= read -r arch; do
    [[ -z "$arch" ]] || sudo dpkg --add-architecture "$arch"
done < "$ROOT/foreign-architectures.txt"

# Keep the replacement VM's Ubuntu mirror configuration.
for key in "$ROOT"/keyrings/*.gpg; do
    sudo install -m 0644 "$key" "/usr/share/keyrings/$(basename "$key")"
done
for name in bamboo-engine-ubuntu-ibus-bamboo-noble.sources google-chrome.sources vscode.sources; do
    sudo install -m 0644 "$ROOT/sources.list.d/$name" "/etc/apt/sources.list.d/$name"
done
sudo apt-get update

failures=()
packages=()
while IFS= read -r package; do
    [[ -z "$package" || "$package" == \#* || "$package" == onvifsim ]] && continue
    candidate=$(apt-cache policy "$package" | awk '/Candidate:/ {print $2; exit}')
    if [[ -z "$candidate" || "$candidate" == '(none)' ]]; then
        echo "Unavailable apt package: $package" >&2
        failures+=("apt:$package")
    else
        packages+=("$package")
    fi
done < "$list"
if ((${#packages[@]})); then
    sudo apt-get install -y "${packages[@]}"
fi

# Rebuilt from checksum-verified installed files because no apt repository has it.
(cd "$ROOT/debs" && sha256sum --check SHA256SUMS)
sudo apt-get install -y "$ROOT/debs/onvifsim_0.1.0-1_amd64.deb"

if ! command -v snap >/dev/null; then
    sudo apt-get install -y snapd
fi
sudo systemctl start snapd.socket
sudo snap wait system seed.loaded
while IFS=$'\t' read -r name channel confinement version revision; do
    [[ "$name" == name || -z "$name" ]] && continue
    if snap list "$name" >/dev/null 2>&1; then
        echo "Snap already installed: $name (keeping its current channel/version)"
        continue
    fi
    flags=("--channel=$channel")
    [[ "$confinement" != classic ]] || flags+=(--classic)
    if ! sudo snap install "$name" "${flags[@]}"; then
        echo "Failed Snap: $name ($channel). Check whether this branch still exists." >&2
        failures+=("snap:$name")
    fi
done < "$ROOT/snap-packages.tsv"

# Reinstate saved holds only after installation.
mapfile -t holds < "$ROOT/apt-holds.txt"
if ((${#holds[@]})); then
    sudo apt-mark hold "${holds[@]}"
fi
if ((${#failures[@]})); then
    printf 'Could not restore: %s\n' "${failures[@]}" >&2
    exit 1
fi
echo "Package restoration complete. Reboot the VM before using desktop applications."
