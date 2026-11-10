#!/usr/bin/env bash
# Instalace aktualizace dat na server (Ubuntu/Debian), spouští se jako root:
#   bash setup.sh
#
# Co udělá:
#  1. nainstaluje git a python3
#  2. založí uživatele "sokol" a pro něj SSH klíč (deploy key) pro GitHub
#  3. po přidání klíče na GitHub naklonuje repozitář
#  4. nastaví systemd časovač: každých 15 minut stáhne data z IS FAČR
#     a při změně je nahraje na GitHub (GitHub pak web sám nasadí)
set -euo pipefail

REPO="git@github.com:scnaplava/sokol-hustenovice.git"
USER_NAME="sokol"
HOME_DIR="/home/$USER_NAME"
APP_DIR="$HOME_DIR/sokol-hustenovice"

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git python3 tzdata ca-certificates openssh-client >/dev/null
timedatectl set-timezone Europe/Prague || true

id "$USER_NAME" >/dev/null 2>&1 || useradd --create-home --shell /bin/bash "$USER_NAME"

sudo -u "$USER_NAME" bash -c '
  mkdir -p ~/.ssh && chmod 700 ~/.ssh
  [ -f ~/.ssh/id_ed25519 ] || ssh-keygen -q -t ed25519 -N "" -C "sokol-hustenovice-server" -f ~/.ssh/id_ed25519
  ssh-keyscan -t ed25519 github.com >> ~/.ssh/known_hosts 2>/dev/null
  sort -u -o ~/.ssh/known_hosts ~/.ssh/known_hosts
'

# Skript jedné aktualizace
cat > "$HOME_DIR/aktualizace.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
cd "$HOME/sokol-hustenovice"
git pull --rebase --quiet
DATA_SOURCE=facr python3 scripts/update_data.py
if ! git diff --quiet; then
  git add web/data/club.json
  git -c user.name="data-bot" -c user.email="data-bot@users.noreply.github.com" \
    commit --quiet -m "Aktualizace dat"
  git push --quiet
fi
EOF
chmod +x "$HOME_DIR/aktualizace.sh"
chown "$USER_NAME:$USER_NAME" "$HOME_DIR/aktualizace.sh"

cat > /etc/systemd/system/sokol-data.service <<EOF
[Unit]
Description=Aktualizace dat webu TJ Sokol Hustenovice z IS FACR
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
User=$USER_NAME
ExecStart=$HOME_DIR/aktualizace.sh
TimeoutStartSec=600
EOF

cat > /etc/systemd/system/sokol-data.timer <<EOF
[Unit]
Description=Kazdych 15 minut aktualizovat data webu TJ Sokol Hustenovice

[Timer]
OnCalendar=*:0/15
RandomizedDelaySec=60
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload

echo
echo "=== Veřejný klíč serveru (deploy key pro GitHub) ==="
cat "$HOME_DIR/.ssh/id_ed25519.pub"
echo "=================================================="
echo "Po přidání klíče na GitHub spusťte: bash setup.sh --dokoncit"

if [ "${1:-}" = "--dokoncit" ]; then
  sudo -u "$USER_NAME" bash -c "[ -d '$APP_DIR/.git' ] || git clone --quiet '$REPO' '$APP_DIR'"
  systemctl enable --now sokol-data.timer
  systemctl start sokol-data.service || true
  systemctl --no-pager status sokol-data.service | tail -n 5 || true
  systemctl list-timers sokol-data.timer --no-pager
fi
