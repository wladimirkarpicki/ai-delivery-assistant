# Agent Plan — ai-delivery-assistant
Last updated: 2026-10-25 12:55
Process: глобальный AGENTS.md — $DSH_HOME/AGENTS.md | Synced: 2026-10-24 13:00 (= Last updated глобала при последней сверке)
Роль: проектный агент (ai-delivery-assistant) — работа с кодинг-сабагентами; задачи — от главного агента (Team Lead) или пользователя.

## Status
- Active focus: 006 — Dashboard v2: seed тест-данных (убрать unknown-доминирование), только осмысленные метрики, минималистичный дизайн, фикс spacing KPI↔grid (баг из 004 — панели прижаты к KPI-полосе).
- Blocked: —
- Risks: orphaned-том pgdata_ai (fs-повреждён, не удаляется) остаётся в vhdx — чистка отложена; Docker Desktop на USB D: умирает при перезагрузках машины (3-й раз: ночь 21→22.10, npipe not found) — каждый нештатный останов = риск порчи томов, перед выключением машины выходить из Docker Desktop вручную; диск C: ~3.6 ГБ free (нормализовано, было 0.6); на origin ~15 устаревших веток (не мешают).

## Tasks
| ID | Task | Status | Branch | AC / Verification | Evidence |
|----|------|--------|--------|------------------|----------|
| 001 | Собрать Docker-образ (FastAPI + React Vite), compose up, мигрировать данные из локального Postgres | completed (merged в main 2026-10-22) | feature/001-docker-fullstack | `docker compose ps → app healthy; curl /api/health → 200; curl / → index.html; curl /docs → 200; DB: 7 projects / 16 meetings / 59 events; pytest → 12 passed` | Build exit 0; api/health 200; / 200 text/html; /docs 200; DB counts match local; compose.yml + schema.sql + monitoring committed; чекап 2026-10-21: контейнеры Up (healthy), /api/health 200, DB 7/16/59; финал 2026-10-22: pytest 12 passed, merge --no-ff в main, push, ветка удалена |
| 002 | Cleanup stale feature branches (19 слияных) | completed | main | `git branch -l` → только main + feature/001-docker-fullstack | Чекап 2026-10-21: локально только main и feature/001; на origin осталось ~15 устаревших веток |
| 003 | Инцидент-ревери: восстановление стека после fs-повреждения тома pgdata_ai + повторная миграция данных + скриншоты 8 страниц | completed | feature/001-docker-fullstack | `docker compose ps → 2 healthy; /api/health → 200; DB counts 7/16/59/9/9/6; 8 валидных PNG 1440x900` | compose down/up на новом томе pgdata_ai2 exit 0; pg_dump 111747 Б → psql restore exit 0; counts exact match; /api/health 200; screenshots 01-08 (169-240 КБ, Pillow-валидны) |
| 004 | Кросс-проектный метрики-дашборд: /api/metrics + recharts (KPI, пай статусов/импактов, donut open items, бары по проектам и владельцам, area-таймлайн) + README-апдейт (Docker, pytest, mojibake) | completed | feature/004-metrics-dashboard | `pnpm --dir frontend build → exit 0; tsc → 0 errors; pytest tests/test_api.py → 16 passed; curl /api/metrics → 200` | Коммиты 37838a7 (backend + 4 теста) / 295c8b2 (recharts-фронт, useTheme+chartTheme) / f83a295 (README Docker/pytest/mojibake); Lead-верификация 2026-10-24: pytest 16 passed 4.67s, ревью api.py (агрегаты пакетные, outerjoin unknown) и DashboardPage, docker rebuild → /api/metrics 200 (totals 7/16/9/59, статусы unknown 5/at risk 1/on track 1, impacts high 4/unknown 5, owners 5 строк), /api/health 200, скриншоты 09-11 light/full/dark (Pillow mean 225/30) |
| 005 | Аутентификация с ролями admin/user по образцу inventory-management-system: users-таблица, JWT HS256, lockout 5 неудач/15 мин, bootstrap-админ, admin-CRUD пользователей, last-admin защита, SPA login/setup/users | completed | feature/005-auth-roles | `без токена /api/projects → 401; user → 403 на /api/users; login lockout → 429; last-admin demote/delete → 400; pytest → 29 passed; build+tsc → 0` | Коммиты ee90b99/7ec771b/c44bcc7/624e24e/c880c8d + e7949c9 (compose JWT_SECRET_KEY); Lead-верификация 2026-10-25: pytest 29 passed, ruff clean; docker-БД: users-DDL + alembic_version→c2f6b8d4a1e9 (psql, эквивалент миграции); стек: 14/14 curl-гейтов PASS (401 без токена, 403 user-роль, 429 lockout, 400 self-delete/last-admin, setup/login 200, метрики под токеном; JWT_SECRET_KEY 64 симв. в контейнере); throwaway-юзеры стёрты (users=0), /setup свободен; скриншоты 12-14 |
| 006 | Dashboard v2: seed тест-данных (убрать unknown-доминирование) + только осмысленные метрики + минималистичный дизайн + фикс spacing KPI↔grid | in_progress | feature/006-dashboard-v2 | `pytest → все зелёные; build+tsc → 0; seed: у 5 тест-проектов реальные статусы, ≥3 демо-проекта, known impacts, owners, activity ≥5 мес.; /api/metrics 200; «воздух» между секциями на скриншотах` | — |

## Task details
### 001 — Docker full-stack build + data migration
Goal: Поднять полный стек ai-delivery-assistant в Docker (FastAPI бэк + React Vite фронт) с миграцией существующих данных из локального PostgreSQL
Scope: Dockerfile (multi-stage), compose.yml, schema.sql, monitoring configs, .dockerignore, tsc-check.sh cleanup, branch cleanup
AC: `docker compose ps → app healthy; curl /api/health → 200; curl / → index.html; curl /docs → 200; API /projects → 7 projects`
Verification: `docker compose ps; curl http://localhost:8001/api/health; curl http://localhost:8001/; curl http://localhost:8001/docs; docker exec ai-delivery-assistant-db-1 psql -c "SELECT 'projects', COUNT(*) FROM projects UNION ALL SELECT 'meetings', COUNT(*) FROM meetings..."`
Constraints: Disk space via D: junction; Docker Desktop auto-update disabled; postgres:16 base image; pytest test_api.py needs python-multipart env fix

### 002 — Cleanup stale feature branches
Goal: Удалить 19 устаревших feature-веток, уже слияных с main, чтобы сократить мусор в repos
Scope: git branch -d for all merged branches
AC: `git branch` shows only `main` and current feature branch; no stale `feature/*` left
Verification: `git branch -l` output
Evidence: all 19 branches deleted (listed in commit)
Constraints: None

### 003 — Инцидент-ревери + тёмные скриншоты
Goal: Восстановить стек после fs-повреждения, повторно мигрировать данные, снять скриншоты светлой и тёмной темы
Scope: pgdata_ai2 + повторная миграция + 8 скриншотов light + 8 скриншотов dark (--force-dark-mode)
AC: 16 валидных PNG 1440x900; данные 7/16/59/9/9/6
Verification: `ls screenshots/*.png` → 16 файлов; Pillow validation pass
Constraints: USB disk latency, Docker restart after crash

### 004 — Кросс-проектный метрики-дашборд
Goal: Красивый дашборд с метриками по всем проектам: пайчарты и другие типы графиков (recharts), светл/тём темы.
Scope: api.py — новый /api/metrics (totals, status_distribution, open_items_mix, per_project, risk_impacts, activity_timeline, action_owners); frontend — recharts@3, DashboardPage: KPI-плитки + сетка графиков + существующие карточки ниже; useTheme-хук (data-theme) + палитры light/dark; тесты /api/metrics; README: Docker-quickstart, метрики-дашборд, pytest-команда, mojibake-фикс («вЂ”» → «—»).
AC: /api/metrics → 200 со всеми агрегатами; дашборд рендерит KPI + ≥6 графиков в обеих темах; build + tsc → exit 0; pytest → все зелёные (12 старых не сломаны); docker rebuild → /api/metrics 200 на :8001.
Verification: pnpm --dir frontend build; pnpm --dir frontend typecheck; python -m pytest tests/test_api.py; docker compose up -d --build; curl http://127.0.0.1:8001/api/metrics.
Constraints: recharts — единственная новая зависимость; не трогать models.py/схему БД и /api/dashboard; коммиты только на feature-ветке, git add по конкретным файлам (screenshots/ и AGENT_PLAN не коммитить — план ведёт Lead).

### 005 — Аутентификация с ролями admin/user
Goal: Доступ к приложению только после логина; роли admin (управление пользователями) и user; паттерн 1:1 с inventory-management-system.
Scope: models.py — User(id, username unique, password_hash, role user|admin) + Alembic-миграция users; api.py — auth-блок: POST /api/auth/setup (bootstrap первого admin, только при пустой users), POST /api/auth/login (JWT HS256 access_token + lockout: 5 неудач → 429 на 15 мин, in-memory), GET /api/auth/me, POST /api/auth/password (self, с current_password); admin-CRUD: GET/POST /api/users, PATCH/DELETE /api/users/{id} (no self-delete, last-admin защита), POST /api/users/{id}/password; зависимости get_current_user/require_admin на всех бизнес-роутах (кроме /api/health — docker healthcheck); PyJWT + werkzeug.security (requirements.txt); SECRET_KEY через config_loader/.env; frontend: auth-слой (AuthProvider/useAuth), Bearer-токен из localStorage, RequireAuth + redirect /login, страницы Login/Setup/Password/Users (admin), AppShell — текущий юзер + logout; тесты: 401/403/429/last-admin/user-CRUD + bearer-фикстуры для существующих тестов.
AC: без токена все бизнес-API → 401 (кроме /api/health и auth); user → 403 на /api/users; admin управляет пользователями; lockout и last-admin срабатывают; SPA редиректит на /login, setup при пустой users; 12 старых + новые тесты зелёные; build + tsc → 0.
Verification: python -m pytest tests/test_api.py; pnpm --dir frontend build; docker compose up -d --build; curl: /api/health → 200 без токена; /api/projects без токена → 401; login → 200 токен; user-токен → 403 на /api/users.
Constraints: паттерн и UX — как inventory-management-system (JWT bearer, in-memory lockout, localStorage-токен); /api/health остаётся публичным (docker healthcheck); не ломать 004-метрики; пароли только werkzeug-хэш; SECRET_KEY не коммитить (.env.example — заглушка). Начало 005 — после merge 004.

### 006 — Dashboard v2: тест-данные + осмысленные метрики + минималистичный дизайн
Goal: Дашборд без unknown-доминирования и визуального шума: реалистичные тест-данные, только осмысленные метрики, минималистичный «крутой» дизайн; фикс бага — «воздух» между KPI-полосой и сеткой графиков.
Scope: scripts/seed_demo_data.py — идемпотентный seed (по образцу inventory seed-скриптов): 5 тест-проектов получают реальные ProjectState.delivery_status (on track/at risk/blocked/delivered — выбрать осмысленно), +3 новых демо-проекта с полными данными на ~6 месяцев (meetings c created_at в прошлом, risks impact high/medium/low open+resolved с resolved_at, blockers, action_items с owners/due dates open+completed, decisions, history_events; канонические заголовки уникальны; демо-сущности помечены и пересоздаются при повторном запуске); /api/metrics: totals+resolution_rate+meetings_last_30d, risk_impacts, activity_timeline, per_project, status_distribution, action_owners — под новые метрики; DashboardPage v2: KPI 4-6 осмысленных, 5 графиков (status donut, risk profile donut open-by-impact, open work per project stacked, actions by owner, activity area wide) — УБРАТЬ meetings-per-project bar, open-items-mix donut, вложенный двухкольцевой donut (дублируют KPI / не-минималистичны); CSS: gap между KPI-строкой и grid + минималистичная стилизация (крупные цифры KPI, muted-лейблы, лёгкие оси); README: секция seed-скрипта.
AC: seed применён к docker-БД: 0 unknown-статусов у 5 тест-проектов, ≥3 демо-проекта, risks только с known impacts, owners заполнены, activity ≥5 месяцев; дашборд: KPI + 5 осмысленных графиков в обеих темах; «воздух» между секциями виден на скриншотах; pytest зелёные (29 + обновлённые metrics-тесты); build+tsc → 0.
Verification: python -m pytest tests/test_api.py; pnpm --dir frontend build; docker compose exec -T app python - < scripts/seed_demo_data.py; curl http://127.0.0.1:8001/api/metrics (Bearer); скриншоты light/dark.
Constraints: recharts остаётся (по ресёрчу: tremor/shadcn требуют Tailwind — конфликт с собственным дизайн-языком; shadcn charts сами = recharts со стилями; nivo = полная переписка чартов 004); данные пользователя (проекты inventory-management-system и ai-delivery-assistant) не трогать — только 5 тест-проектов + новые демо; /api/dashboard не менять; auth-паттерн не менять.

## Decisions
- 2026-10-18 — план создан (миграция на глобальный шаблон v2); процесс живёт в `.dsh/AGENTS.md`, здесь — только состояние.
- 2026-10-20 — Docker Desktop на D:\Docker\wsl через NTFS-junction (Infra / Machine in ENVIRONMENT.md).
- 2026-10-20 — Dockerfile копирует providers/, services/, static/ + frontend-build stage (фикс ImportError при старте).
- 2026-10-20 — compose.yml использует postgres:16 (совпадает с inventory), schema.sql заменён реальным дампом из локального PG 18 (промаркированный \restrict закомментирован для совместимости psql 16).
- 2026-10-20 — tsc-check.sh удалён (scratch-файл).
- 2026-10-20 — Docker Desktop auto-update отключён (AutoDownloadUpdates=False, DisableUpdate=True) через settings-store.json, так как апдейт не влезал на диск C:.
- 2026-10-21 — 19 feature-веток слияния с main удалены (feature/001-docker-fullstack сохранён).
- 2026-10-21 — План Synced: глобал 18:48, план 13:20.
- 2026-10-21 — Инцидент pgdata_ai: fs-повреждение (EBADMSG) после нештатного останова Docker Desktop; точечное лечение (rm файлов, docker volume rm) невозможно — переименовали том в compose.yml на pgdata_ai2, старый оставлен orphaned для безопасной чистки позже; данные восстановлены повторным pg_dump из локального PG 18.4 (источник истины жив, localhost:5432).
- 2026-10-22 — Merge ветки 001 в main (merge --no-ff) выполнен после зелёных тестов (12 passed) — блокер multipart исчез сам: пакет python-multipart корректно встал в системный Python, код проекта не менялся; ветка удалена локально и на origin; проект переведён на паузу (по прямому запросу пользователя).
- 2026-10-24 — Пауза снята прямым запросом пользователя: заказан метрики-дашборд (004). Выбран recharts@3 (React 19, SVG-чарты, темизация через useTheme-хук на data-theme); README-апдейт влит в 004 — README от 18.10 не отражал Docker-стек и pytest-команду, содержал mojibake «вЂ”».
- 2026-10-24 — Задача 005 (auth с ролями admin/user) заказана пользователем «как в inventory-management-system»: паттерн копируется с того проекта (JWT HS256 + PyJWT, werkzeug-хэши, in-memory lockout 5/15 мин, bootstrap-setup, admin-CRUD, last-admin защита, SPA AuthProvider/RequireAuth/localStorage) с адаптацией к SQLAlchemy + Alembic вместо raw psycopg; /api/health остаётся без auth ради docker healthcheck; старт 005 — после merge 004.
- 2026-10-25 — Деплой 005: users-миграция применена к docker-БД напрямую через psql (DDL из c2f6b8d4a1e9 + бамп alembic_version) — образ не содержит migrations/, Docker-стек управляется schema.sql на fresh-томах; JWT_SECRET_KEY проброшен в compose environment из .env (сгенерирован, не в репо) — иначе ephemeral-ключ сбрасывал бы сессии при каждом рестарте; ruff B008 ignore (FastAPI Depends в дефолтах — канон). Первый вход пользователя — /setup.
- 2026-10-25 — 006 (по прямому запросу пользователя: осмысленные метрики + минимализм + «крутая» UI-библиотека + фикс spacing): ресёрч дал nivo/shadcn-ui/tremor; выбран путь «recharts + минимальная стилизация на своих токенах» — tremor и shadcn тянут Tailwind (вторая дизайн-система в конфликт), nivo требует полной переписки чартов 004, а shadcn charts подтверждают паттерн (они и есть recharts со стилями). Метрики сокращены до осмысленных: KPI + 5 графиков, «unknown» → «not started», вложенный donut убран. Seed — по паттерну seed-скриптов inventory-management-system.

## Learnings
- 2026-10-20 — Инфраструктура: Docker Desktop (WSL2) на внешнем накопителе D: (junction) — см. `ENVIRONMENT.md` (Infra / Machine).
- 2026-10-18 — работа feature/consolidation-review-queue (app.py, models.py, project_memory.py, project_overview.html) закончилась прямыми коммитами в main — дальше строго через ветки и PR.
- 2026-10-20 — Healthcheck postgres в compose требует готовность БД; схема инициализируется через schema.sql в initdb.d; при смене схемы нужно пересоздать том pgdata_ai.
- 2026-10-21 — Очистка 19 веток: git branch -d для всех веток, слияных с main, сокращает репозиторий; сохранён только feature/001-docker-fullstack и main.
- 2026-10-21 — IMAGE ID ai-delivery-assistant-app расходится между контекстами (f5ec84dbf023 → фактический 33bda2987e52, тот же created-at/размер) — образ идентифицировать по имени + created-at; чистка локальных веток (002) не чистит origin.
- 2026-10-21 — EBADMSG в pgdata volume = повреждение fs-уровня (не битые данные): postgres-entrypoint падает на chown ДО старта сервера, crash-loop (RestartCount=7); rm/volume rm изнутри Docker тоже EBADMSG. Лечение — свежий том + повторная миграция из внешнего источника, а не fsck на живом vhdx (в нём же данные inventory).
- 2026-10-21 — Скриншоты SPA: Chrome `--headless=new --virtual-time-budget=15000 --window-size=1440,900` на `127.0.0.1` (не `localhost`); перед съёмкой сначала проверить стек (`/api/health`), иначе снимутся страницы ошибок Chrome.
- 2026-10-22 — «Пропавший» блокер multipart: падение 12 тестов (2026-10-21) было env-состоянием системного Python (python-multipart доустановился в процессе диагностики), код проекта не виноват; свежий прогон 2026-10-22 — 12 passed без изменений кода. Вывод: перед отладкой «сломанных» тестов перезапускать их в свежем состоянии.

## Next steps
1. Чистка orphaned-тома pgdata_ai (fs-повреждён): только с подтверждения человека — `docker volume rm` в спокойном состоянии Docker, при отказе — вплоть до пересоздания docker_data.vhdx с переносом данных inventory; учесть перед этим стабильность Docker Desktop.
2. (Опционально, при снятии с паузы) интеграционные тесты API endpoints; чистка ~15 устаревших веток на origin (с подтверждением человека); monitoring profile (prometheus+grafana).

## Archive
- ✅ Rewriting the Flask app as FastAPI + React (7110261)
- ✅ Security audit + GitHub Actions (ece6773); Dependabot + SECURITY.md (51bf4db)
- ✅ Type-checking fixes: models.py/api.py (7c2c035)
- ✅ План засеян при миграции на AGENT_PLAN.md (2026-10-18)
- ✅ 001 — Docker full-stack build + data migration (feature/001-docker-fullstack → merged в main 2026-10-22)
- ✅ 002 — Git branch cleanup: 19 merged branches deleted (feature/001-docker-fullstack)
- ✅ 003 — Инцидент-ревери pgdata_ai → pgdata_ai2 + повторная миграция данных + скриншоты 8 страниц (2026-10-21)
- ✅ Merge 001 в main (12 passed, merge --no-ff, ветка удалена локально и на origin) — проект на паузе (2026-10-22)
- ✅ 004 — Метрики-дашборд (/api/metrics + recharts: KPI, пай статусов/импактов, donut, бары, area-таймлайн, обе темы, a11y) — 16 passed, /api/metrics 200 в стеке, скриншоты light/dark (2026-10-24)
- ✅ 005 — Auth admin/user (JWT HS256, lockout, bootstrap-setup, admin-CRUD, last-admin защита, SPA login/setup/users) — 29 passed, 14/14 curl-гейтов в Docker-стеке, скриншоты login/setup (2026-10-25)