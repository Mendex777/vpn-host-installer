#!/usr/bin/env bash
set -Eeuo pipefail
REPO="${VHI_REPOSITORY:-Mendex777/vpn-host-installer}"
REF="${VHI_REF:-main}"
INSTALL_DIR="/opt/vpn-host-installer"
CONFIG_DIR="/etc/vpn-host-installer"
[[ ${EUID} -eq 0 ]] || { echo "ERROR: run as root" >&2; exit 1; }
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv curl ca-certificates
tmp_dir="$(mktemp -d)"
trap 'rm -rf -- "$tmp_dir"' EXIT
curl -fsSL "https://github.com/${REPO}/archive/refs/heads/${REF}.tar.gz" -o "$tmp_dir/source.tar.gz"
tar -xzf "$tmp_dir/source.tar.gz" -C "$tmp_dir"
source_dir="$(find "$tmp_dir" -mindepth 1 -maxdepth 1 -type d | head -n1)"
mkdir -p "$INSTALL_DIR" "$CONFIG_DIR"
find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
cp -a "$source_dir"/. "$INSTALL_DIR"/
python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install -q --disable-pip-version-check -r "$INSTALL_DIR/requirements.txt"
if [[ ! -f "$CONFIG_DIR/config.yaml" ]]; then
  install -m 600 "$INSTALL_DIR/config.yaml" "$CONFIG_DIR/config.yaml"
  echo "Created $CONFIG_DIR/config.yaml. Edit it, then run:" >&2
  echo "  $INSTALL_DIR/.venv/bin/python $INSTALL_DIR/install.py" >&2
  exit 2
fi
exec "$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/install.py" "$@"
