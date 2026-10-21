# Agent Plan — ai-delivery-assistant
Last updated: 2026-10-21 21:30
Process: глобальный AGENTS.md — $DSH_HOME/AGENTS.md | Synced: 2026-10-21 20:42 (= Last updated глобала при последней сверке)
Роль: проектный агент (ai-delivery-assistant) — работа с кодинг-сабагентами; задачи — от главного агента (Team Lead) или пользователя.

## Status
- Active focus: стек восстановлен после инцидента 2026-10-21 ~20:00 (повреждение fs-тома pgdata_ai, EBADMSG на base/16384/24680-24681, crash-loop db): том в compose.yml переименован в pgdata_ai2, initdb+schema.sql заново, данные повторно мигрированы из локального PG 18.4 и верифицированы (7/16/59/9/9/6; /api/health 200, /api/projects 7); 8 скриншотов страниц (screenshots/*.png, Chrome headless 1440x900) переданы пользователю.
- Blocked: merge ветки 001 в main — 12 тестов test_api.py упали из-за env-опроса multipart (библиотека multipart 0.0.32 установлена, но тесты ждут версию > 0.0.12 — issue в тест-суйте, а не в коде); чекап 2026-10-21: lastfailed = ровно 12 тестов; feature/001-docker-fullstack на 2 коммита впереди main (4d7a1d3, df1ed52), запушена в origin, merge не выполнен (§3: сначала зелёные тесты).
- Risks: orphaned-том pgdata_ai (fs повреждён, `docker volume rm` и `rm` дают EBADMSG) остаётся в vhdx — чистка отложена, не трогать без fs-инструментов; Docker Desktop на USB D: умирает при перезагрузках машины (дважды за 2026-10-20..21) — каждый нештатный останов = риск порчи томов; диск C: критичен (0.58 ГБ free); на origin ~15 устаревших веток.

## Tasks
| ID | Task | Status | Branch | AC / Verification | Evidence |
|----|------|--------|--------|------------------|----------|
| 001 | Собрать Docker-образ (FastAPI + React Vite), compose up, мигрировать данные из локального Postgres | completed (merge в main pending) | feature/001-docker-fullstack | `docker compose ps → app healthy; curl /api/health → 200; curl / → index.html; curl /docs → 200; DB: 7 projects / 16 meetings / 59 events` | Build exit 0; api/health 200; / 200 text/html; /docs 200; DB counts match local; compose.yml + schema.sql + monitoring committed; чекап 2026-10-21: контейнеры Up (healthy), /api/health 200, DB 7/16/59 подтверждены; ветка +2 коммита к main (4d7a1d3, df1ed52), запушена, merge не выполнен |
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

## Decisions
- 2026-10-18 — план создан (миграция на глобальный шаблон v2); процесс живёт в `.dsh/AGENTS.md`, здесь — только состояние.
- 2026-10-20 — Docker Desktop на D:\Docker\wsl через NTFS-junction (Infra / Machine in ENVIRONMENT.md).
- 2026-10-20 — Dockerfile копирует providers/, services/, static/ + frontend-build stage (фикс ImportError при старте).
- 2026-10-20 — compose.yml использует postgres:16 (совпадает с inventory), schema.sql заменён реальным дампом из локального PG 18 (промаркированный \restrict закомментирован для совместимости psql 16).
- 2026-10-20 — tsc-check.sh удалён (scratch-файл).
- 2026-10-20 — Docker Desktop auto-update отключён (AutoDownloadUpdates=False, DisableUpdate=True) через settings-store.json, так как апдейт не влезал на диск C:.
- 2026-10-21 — 19 feature-веток слияния с main удалены (feature/001-docker-fullstack сохранён).
- 2026-10-21 — План Synced: глобал 18:48, план 13:20.
- 2026-10-21 — Чекап (проектный агент, read-only): Synced актуален (глобал 18:48 = план); Docker-стек running healthy, evidence 001 подтверждён (/api/health 200, DB 7/16/59); ветка 001 запушена в origin, но merge в main отложен до зелёных тестов (§3); Task 002 внесён в таблицу Tasks; origin/main = d080417 (по локальным remote-refs, без fetch).
- 2026-10-21 — Инцидент pgdata_ai: fs-повреждение (EBADMSG) после нештатного останова Docker Desktop; точечное лечение (rm файлов, docker volume rm) невозможно — переименовали том в compose.yml на pgdata_ai2, старый оставлен orphaned для безопасной чистки позже; данные восстановлены повторным pg_dump из локального PG 18.4 (источник истины жив, localhost:5432).

## Learnings
- 2026-10-20 — Инфраструктура: Docker Desktop (WSL2) на внешнем накопителе D: (junction) — см. `ENVIRONMENT.md` (Infra / Machine).
- 2026-10-18 — работа feature/consolidation-review-queue (app.py, models.py, project_memory.py, project_overview.html) закончилась прямыми коммитами в main — дальше строго через ветки и PR.
- 2026-10-20 — Healthcheck postgres в compose требует готовность БД; схема инициализируется через schema.sql в initdb.d; при смене схемы нужно пересоздать том pgdata_ai.
- 2026-10-21 — Очистка 19 веток: git branch -d для всех веток, слияных с main, сокращает репозиторий; сохранён только feature/001-docker-fullstack и main.
- 2026-10-21 — IMAGE ID ai-delivery-assistant-app расходится между контекстами (f5ec84dbf023 → фактический 33bda2987e52, тот же created-at/размер) — образ идентифицировать по имени + created-at; чистка локальных веток (002) не чистит origin.
- 2026-10-21 — EBADMSG в pgdata volume = повреждение fs-уровня (не битые данные): postgres-entrypoint падает на chown ДО старта сервера, crash-loop (RestartCount=7); rm/volume rm изнутри Docker тоже EBADMSG. Лечение — свежий том + повторная миграция из внешнего источника, а не fsck на живом vhdx (в нём же данные inventory).
- 2026-10-21 — Скриншоты SPA: Chrome `--headless=new --virtual-time-budget=15000 --window-size=1440,900` на `127.0.0.1` (не `localhost`); перед съёмкой сначала проверить стек (`/api/health`), иначе снимутся страницы ошибок Chrome.

## Next steps
1. Исправить тестовые зависимости: `pip install -e ".[dev]"` или добавить `python-multipart` в requirements.txt с версией > 0.0.12; либо исправить проверку в fastapi/dependencies/utils.py — блокер для merge ветки 001 (§3).
2. После зелёных тестов: PR/merge feature/001-docker-fullstack в main (evidence — Tasks 001/003), затем удалить ветку локально и на origin.
3. Чистка orphaned-тома pgdata_ai (fs-повреждён): только с подтверждением человека — `docker volume rm` в спокойном состоянии Docker, при отказе — вплоть до пересоздания docker_data.vhdx с переносом данных inventory; учесть перед этим стабильность Docker Desktop.
4. (Опционально) интеграционные тесты API endpoints; чистка ~15 устаревших веток на origin (с подтверждением человека); monitoring profile (prometheus+grafana) при необходимости.

## Archive
- ✅ Rewriting the Flask app as FastAPI + React (7110261)
- ✅ Security audit + GitHub Actions (ece6773); Dependabot + SECURITY.md (51bf4db)
- ✅ Type-checking fixes: models.py/api.py (7c2c035)
- ✅ План засеян при миграции на AGENT_PLAN.md (2026-10-18)
- ✅ 001 — Docker full-stack build + data migration (feature/001-docker-fullstack)
- ✅ 002 — Git branch cleanup: 19 merged branches deleted (feature/001-docker-fullstack)
- ✅ 003 — Инцидент-ревери pgdata_ai → pgdata_ai2 + повторная миграция данных + скриншоты 8 страниц (2026-10-21)