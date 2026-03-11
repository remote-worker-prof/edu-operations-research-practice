# Git, SSH, ssh-agent и GitHub: практический учебник для этого проекта

Этот документ описывает полный рабочий цикл: от установки Git до безопасной
работы через SSH‑ключи и `ssh-agent`. Текст ориентирован на начинающих
студентов и адаптирован под репозиторий `edu-operations-research-practice`.

## 1. Что такое Git и зачем он нужен

Git — система контроля версий. Она позволяет:

- хранить историю изменений;
- возвращаться к прошлым состояниям;
- работать в команде без конфликтов;
- публиковать код на GitHub.

Git работает локально и не требует интернета для большинства операций.
GitHub — удалённый хостинг для репозиториев.

## 2. Установка Git и базовая проверка

Проверить версию:

```bash
git --version
```

Если Git не установлен (пример для Debian/Ubuntu):

```bash
sudo apt update
sudo apt install git
```

## 3. Базовая настройка Git

Укажите имя и email для коммитов (глобально или локально в проекте).

Глобально:

```bash
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

Локально для одного репозитория:

```bash
git config user.name "Your Name"
git config user.email "you@example.com"
```

Проверка:

```bash
git config --list
```

## 4. Основной цикл работы с Git

Типичный цикл:

1. Изменить файлы.
2. Проверить статус:

```bash
git status
```

3. Добавить изменения в индекс:

```bash
git add -A
```

4. Сделать коммит:

```bash
git commit -m "Your message"
```

5. Отправить на сервер:

```bash
git push
```

## 5. Ветки: кратко и по делу

Ветки позволяют параллельно вести работу над разными задачами.

Создание ветки:

```bash
git checkout -b feature/new-section
```

Список веток:

```bash
git branch
```

Переключение:

```bash
git checkout main
```

Слияние:

```bash
git merge feature/new-section
```

## 6. Удалённые репозитории (remote)

Просмотр текущих remote:

```bash
git remote -v
```

Добавление remote:

```bash
git remote add origin git@github.com:<owner>/<repo>.git
```

Смена remote:

```bash
git remote set-url origin git@github.com:<owner>/<repo>.git
```

## 7. GitHub: как всё связано

GitHub хранит репозитории и позволяет:

- просматривать историю;
- принимать pull requests;
- запускать Actions;
- публиковать сайты через Pages.

GitHub работает поверх Git и дополняет его.

## 8. Что такое SSH и зачем он нужен

SSH — безопасный протокол для доступа к удалённым серверам. В Git‑контексте
он используется, чтобы подключаться к GitHub без пароля (через ключ).

Вместо HTTPS:

```
https://github.com/<owner>/<repo>.git
```

используют SSH:

```
git@github.com:<owner>/<repo>.git
```

## 9. Генерация SSH‑ключа

Рекомендуемый алгоритм — `ed25519`.

```bash
ssh-keygen -t ed25519 -C "you@example.com"
```

По умолчанию ключи сохраняются в `~/.ssh/`:

- приватный: `id_ed25519`
- публичный: `id_ed25519.pub`

## 10. Добавление ключа в GitHub

1. Откройте файл публичного ключа:

```bash
cat ~/.ssh/id_ed25519.pub
```

2. Скопируйте содержимое.
3. GitHub → Settings → SSH and GPG keys → New SSH key.
4. Вставьте ключ и сохраните.

## 11. Проверка SSH‑подключения

```bash
ssh -T git@github.com
```

Ожидается ответ вида:

```
Hi <username>! You've successfully authenticated, but GitHub does not provide shell access.
```

## 12. ssh-agent: работа без постоянного пароля

Если ключ защищён паролем, его можно загрузить в `ssh-agent`. Тогда Git будет
использовать ключ без повторного ввода.

Разовый запуск:

```bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
```

Для сохранения агента между сессиями в WSL:

```bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519_github
printf 'export SSH_AUTH_SOCK=%s\nexport SSH_AGENT_PID=%s\n' "$SSH_AUTH_SOCK" "$SSH_AGENT_PID" > ~/.ssh/agent.env
chmod 600 ~/.ssh/agent.env
```

Далее достаточно подгружать окружение:

```bash
source ~/.ssh/agent.env
```

## 13. SSH‑конфиг для нескольких аккаунтов

Если нужно использовать разные аккаунты GitHub, удобно завести алиасы в
`~/.ssh/config`:

```sshconfig
Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/id_ed25519_github
  AddKeysToAgent yes
  IdentitiesOnly yes
  PreferredAuthentications publickey

Host github-worker
  HostName github.com
  User git
  IdentityFile ~/.ssh/id_ed25519_github_worker
  AddKeysToAgent yes
  IdentitiesOnly yes
  PreferredAuthentications publickey
```

Тогда можно выбрать нужный ключ через remote:

```bash
git remote set-url origin git@github-worker:algorithmic-planetoid/edu-operations-research-practice.git
```

## 14. Частые ошибки и их причины

- **Permission denied (publickey)** — ключ не добавлен в GitHub или не подхвачен агентом.
- **Repository not found** — неверный remote или нет доступа.
- **Host key verification failed** — впервые подключаетесь и не подтвердили ключ хоста.
- **Multiple keys offered** — в конфиге не указан `IdentitiesOnly yes`.

## 15. Практический чек‑лист

1. `git --version` — Git установлен.
2. `git config --global user.name/user.email` — имя и email заданы.
3. `ssh-keygen -t ed25519` — ключ создан.
4. `ssh -T git@github.com` — проверка связи.
5. `git remote -v` — remote корректный.
6. `git push` — изменения уходят на GitHub.

## 16. Мини‑глоссарий

- **commit** — снимок изменений.
- **branch** — ветка разработки.
- **remote** — удалённый репозиторий.
- **origin** — имя remote по умолчанию.
- **push** — отправка изменений.
- **pull** — получение изменений.
- **clone** — загрузка репозитория на локальную машину.

## Источники

- https://git-scm.com/doc
- https://docs.github.com/en/authentication/connecting-to-github-with-ssh
- https://docs.github.com/en/get-started/quickstart/set-up-git
- https://docs.github.com/en/get-started/using-git/about-git
