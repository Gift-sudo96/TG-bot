#!/usr/bin/env bash
# Ставить бота як службу systemd на Linux-сервері.
#
#   bash deploy/install.sh
#
# Запускати з теки проєкту, від звичайного користувача (не root) —
# скрипт сам попросить sudo там, де потрібно.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE="tg-reminder-bot"
RUN_AS="$(id -un)"

echo "Тека проєкту : $DIR"
echo "Користувач   : $RUN_AS"
echo

# --------------------------------------------------- 1. системні пакети
if command -v apt-get >/dev/null 2>&1; then
  echo "[1/5] Ставлю python3 і venv..."
  sudo apt-get update -qq
  sudo apt-get install -y -qq python3 python3-venv python3-pip
elif command -v dnf >/dev/null 2>&1; then
  echo "[1/5] Ставлю python3 і venv..."
  sudo dnf install -y -q python3 python3-pip
else
  echo "[1/5] Невідомий пакетний менеджер — переконайся, що python3 уже є."
fi

# ------------------------------------------------------ 2. залежності
echo "[2/5] Створюю venv і ставлю бібліотеки..."
python3 -m venv "$DIR/venv"
"$DIR/venv/bin/pip" install --quiet --upgrade pip
"$DIR/venv/bin/pip" install --quiet -r "$DIR/requirements.txt"

# ------------------------------------------------------------ 3. .env
if [ ! -f "$DIR/.env" ]; then
  cp "$DIR/.env.example" "$DIR/.env"
  chmod 600 "$DIR/.env"
  echo
  echo "=================================================================="
  echo " Створено файл $DIR/.env"
  echo
  echo " Відкрий його:   nano $DIR/.env"
  echo " Впиши BOT_TOKEN, ALLOWED_IDS і NAMES, збережи (Ctrl+O, Enter,"
  echo " Ctrl+X), потім запусти цей скрипт ще раз."
  echo "=================================================================="
  exit 1
fi

chmod 600 "$DIR/.env"      # токен має бути видно лише власнику

if grep -q "your-token-here" "$DIR/.env"; then
  echo "У .env досі заготовка замість токена. Впиши справжній і запусти знову."
  exit 1
fi
if grep -qE "^ALLOWED_IDS=(111111111|$)" "$DIR/.env"; then
  echo "У .env не заповнений ALLOWED_IDS. Впиши свій Telegram ID і запусти знову."
  exit 1
fi

# --------------------------------------------------------- 4. systemd
echo "[3/5] Реєструю службу systemd..."
sudo tee /etc/systemd/system/$SERVICE.service >/dev/null <<UNIT
[Unit]
Description=Telegram reminder bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$RUN_AS
WorkingDirectory=$DIR
ExecStart=$DIR/venv/bin/python $DIR/bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now $SERVICE

# --------------------------------------------------- 5. щоденний бекап
# Таймер systemd, а не cron: в образах Ubuntu Minimal cron не встановлений,
# а systemd є завжди. Persistent=true дожене пропущений запуск після простою.
echo "[4/5] Вмикаю щоденний бекап бази..."
sudo tee /etc/systemd/system/$SERVICE-backup.service >/dev/null <<UNIT
[Unit]
Description=Backup $SERVICE database

[Service]
Type=oneshot
User=$RUN_AS
WorkingDirectory=$DIR
ExecStart=$DIR/venv/bin/python $DIR/deploy/backup.py
UNIT

sudo tee /etc/systemd/system/$SERVICE-backup.timer >/dev/null <<'UNIT'
[Unit]
Description=Daily database backup

[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now $SERVICE-backup.timer

echo "[5/5] Перевіряю..."
sleep 4
if systemctl is-active --quiet $SERVICE; then
  echo
  echo "=================================================================="
  echo " Готово. Бот працює і підніматиметься сам після перезавантаження."
  echo
  echo "   стан    : sudo systemctl status $SERVICE"
  echo "   лог     : journalctl -u $SERVICE -f"
  echo "   рестарт : sudo systemctl restart $SERVICE"
  echo "   стоп    : sudo systemctl stop $SERVICE"
  echo "=================================================================="
else
  echo
  echo "Служба не піднялась. Причина:"
  sudo journalctl -u $SERVICE -n 30 --no-pager
  exit 1
fi
