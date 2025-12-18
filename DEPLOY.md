# 🚀 Быстрый деплой на сервер

## 1. Перенос проекта на сервер

### С вашего Mac:

```bash
# Упакуйте проект (из папки vk-tg-autoposter)
cd /Users/virprom/vk-tg-autoposter
tar -czf vk-tg-autoposter.tar.gz \
  database/ \
  scripts/ \
  .env.example \
  .gitignore \
  docker-compose.yml \
  requirements.txt \
  README.md \
  DEPLOY.md

# Скопируйте на сервер
scp vk-tg-autoposter.tar.gz user@your-server:/tmp/

# Также скопируйте ваш архив фото (2400 штук)
scp -r /path/to/your/archive/* user@your-server:/tmp/archive/
```

---

## 2. Установка на сервере

### Подключитесь к серверу:

```bash
ssh user@your-server
```

### Распакуйте проект:

```bash
# Создайте папку
sudo mkdir -p /opt/vk-tg-autoposter
sudo chown $USER:$USER /opt/vk-tg-autoposter

# Распакуйте
cd /opt/vk-tg-autoposter
tar -xzf /tmp/vk-tg-autoposter.tar.gz

# Переместите архив фото
mkdir -p photos/archive
mv /tmp/archive/* photos/archive/
```

### Установите Docker (если ещё нет):

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y docker.io docker-compose-plugin

# Добавьте себя в группу docker
sudo usermod -aG docker $USER
newgrp docker

# Проверка
docker --version
docker compose version
```

---

## 3. Настройка

```bash
cd /opt/vk-tg-autoposter

# Создайте .env из примера
cp .env.example .env

# Проверьте настройки (всё уже заполнено, но можно уточнить)
cat .env
```

**⚠️ ВАЖНО:** Добавьте бота в канал `@kotatastrax` **админом** с правом "Post messages"!

---

## 4. Инициализация

```bash
# Создайте папки
mkdir -p data photos/queue

# Инициализируйте базу данных
docker compose run --rm bot python database/init_db.py

# Загрузите архив в базу (займёт 2-5 минут)
docker compose run --rm bot python scripts/init_archive.py
```

Вы увидите:
```
📂 Scanning archive: /app/photos/archive
  ⏳ Processed 100 photos...
  ⏳ Processed 200 photos...
  ...
✅ Archive scan complete:
   Added: 2400
   Skipped (duplicates): 0
   Errors: 0
```

---

## 5. Запуск

```bash
# Запустите все сервисы
docker compose up -d

# Проверьте логи
docker compose logs -f
```

Вы должны увидеть:
```
vk-tg-bot     | ✅ Bot started
vk-tg-bot     |    Channel: @kotatastrax
vk-tg-bot     |    Admin: 494917175
vk-tg-bot     |    Posting schedule: 06:00, 15:00, 22:00 (Krasnoyarsk)
vk-fetcher    | ✅ Database initialized at /app/data/queue.db
```

---

## 6. Проверка

### Отправьте боту команду `/stats`:

Откройте бота в Telegram и напишите `/stats`. Вы должны увидеть:

```
📊 Статистика очереди:

⏳ В очереди:
   📂 archive: 2400

✅ Опубликовано: 0
```

### Проверьте VK-загрузчик:

```bash
# Вручную запустите загрузку из VK
docker compose run --rm vk_fetcher python scripts/vk_fetcher.py
```

Вы увидите:
```
🔍 Fetching posts from VK: kot9ta_strah
  ✅ Added: vk_12345_67890.jpg
✅ VK fetch complete: added 5, skipped 0
```

---

## 7. Автозапуск при перезагрузке сервера

```bash
# Создайте systemd unit
sudo nano /etc/systemd/system/vk-tg-autoposter.service
```

Вставьте:
```ini
[Unit]
Description=VK to TG Auto Poster
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/vk-tg-autoposter
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
User=your_username

[Install]
WantedBy=multi-user.target
```

Замените `your_username` на ваш пользователь (команда `whoami`).

```bash
# Активируйте
sudo systemctl daemon-reload
sudo systemctl enable vk-tg-autoposter
sudo systemctl start vk-tg-autoposter

# Проверка
sudo systemctl status vk-tg-autoposter
```

---

## ✅ Готово!

Система работает! Первый пост будет в **06:00 по Красноярску**.

### Быстрые команды:

```bash
# Логи
docker compose logs -f

# Статистика
# (напишите боту /stats в Telegram)

# Перезапуск
docker compose restart

# Остановка
docker compose down

# Обновление .env
nano .env
docker compose restart
```

---

## 🔐 После запуска (безопасность)

1. **Перевыпустите VK токен:**
   ```
   https://vk.com/apps?act=manage
   → Удалите приложение
   → Создайте новое
   → Получите новый токен
   → Обновите .env
   ```

2. **Перевыпустите Telegram Bot токен:**
   ```
   @BotFather → /revoke
   → Обновите .env
   ```

3. **Удалите архив из /tmp:**
   ```bash
   rm -rf /tmp/archive /tmp/vk-tg-autoposter.tar.gz
   ```

---

## 🎉 Всё работает!

Проверьте канал `@kotatastrax` в ближайшее время постинга:
- 🕕 06:00 Красноярск
- 🕒 15:00 Красноярск
- 🕙 22:00 Красноярск
