# Agent Plan — ai-delivery-assistant
Last updated: 2026-10-22 13:50
Process: глобальный AGENTS.md — $DSH_HOME/AGENTS.md | Synced: 2026-10-22 12:43 (= Last updated глобала при последней сверке)
Роль: проектный агент (ai-delivery-assistant) — работа с кодинг-сабагентами; задачи — от главного агента (Team Lead) или пользователя.

## Status
- Active focus: проект на паузе. Ветка 001 смержена в main (merge --no-ff, 2026-10-22), ветка удалена локально и на origin; тесты зелёные: `python -m pytest tests/test_api.py → 12 passed` (2026-10-22 12:44, блокер multipart исчез — пакет корректно установлен в системном Python); GitHub полностью актуален.
- Blocked: —
- Risks: orphaned-том pgdata_ai (fs-повреждён, не удаляется) остаётся в vhdx — чистка отложена; Docker Desktop на USB D: умирает при перезагрузках машины (3-й раз: ночь 21→22.10, npipe not found) — каждый нештатный останов = риск порчи томов, перед выключением машины выходить из Docker Desktop вручную; диск C: критичен (~0.6 ГБ free); на origin ~15 устаревших веток (не мешают).

## Tasks
| ID | Task | Status | Branch | AC / Verification | Evidence |
|----|------|--------|--------|------------------|----------|
| 001 | Собрать Docker-образ (FastAPI + React Vite), compose up, мигрировать данные из локального Postgres | completed (merged в main 2026-10-22) | feature/001-docker-fullstack | `docker compose ps → app healthy; curl /api/health → 200; curl / → index.html; curl /docs → 200; DB: 7 projects / 16 meetings / 59 events; pytest → 12 passed` | Build exit 0; api/health 200; / 200 text/html; /docs 200; DB counts match local; compose.yml + schema.sql + monitoring committed; чекап 2026-10-21: контейнеры Up (healthy), /api/health 200, DB 7/16/59; финал 2026-10-22: pytest 12 passed, merge --no-ff в main, push, ветка удалена |
| 002 | Cleanup stale feature branches (19 слияных) | completed | main | `git branch -l` → только main + feature/001-docker-fullstack | Чекап 2026-10-21: локально только main и feature/001; на origin осталось ~15 устаревших веток |
| 003 | Инцидент-ревери: восстановление стека после fs-повреждения тома pgdata_ai + повторная миграция данных + скриншоты 8 страниц | completed | feature/001-docker-fullstack | `docker compose ps → 2 healthy; /api/health → 200; DB counts 7/16/59/9/9/6; 8 валидных PNG 1440x900` | compose down/up на новом томе pgdata_ai2 exit 0; pg_dump 111747 Б → psql restore exit 0; counts exact match; /api/health 200; screenshots 01-08 (169-240 КБ, Pillow-валидны) |

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