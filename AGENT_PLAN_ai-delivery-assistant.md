# Agent Plan — ai-delivery-assistant
Last updated: 2026-10-20 22:15
Process: глобальный AGENTS.md — $DSH_HOME/AGENTS.md | Synced: 2026-10-20 18:48 (= Last updated глобала при последней сверке)
Роль: проектный агент (ai-delivery-assistant) — работа с кодинг-сабагентами; задачи — от главного агента (Team Lead) или пользователя.

## Status
- Active focus: Docker-стек запущен и проверен — бэк (FastAPI) + фронт (React SPA) в контейнере, БД перенесена из локального Postgres
- Blocked: —
- Risks: в истории есть прямые коммиты в main (7c2c035, ece6773, 7110261) — дисциплина «ветка на задачу»; 20+ устаревших локальных веток

## Tasks
| ID | Task | Status | Branch | AC / Verification | Evidence |
|----|------|--------|--------|------------------|----------|
| 001 | Собрать Docker-образ (FastAPI + React Vite), compose up, мигрировать данные из локального Postgres | completed | feature/001-docker-fullstack | `docker compose ps → app healthy; curl /api/health → 200; curl / → index.html; curl /docs → 200; DB: 7 projects / 16 meetings / 59 events` | Build exit 0; api/health 200; / 200 text/html; /docs 200; DB counts match local |

## Task details
### 001 — Docker full-stack build + data migration
Goal: Поднять полный стек ai-delivery-assistant в Docker (FastAPI бэк + React Vite фронт) с миграцией существующих данных из локального PostgreSQL
Scope: Dockerfile (multi-stage), compose.yml, schema.sql, monitoring configs, .dockerignore, tsc-check.sh cleanup
AC: `docker compose ps → app healthy; curl /api/health → 200; curl / → index.html; curl /docs → 200; API /projects → 7 projects`
Verification: `docker compose ps; curl http://localhost:8001/api/health; curl http://localhost:8001/; curl http://localhost:8001/docs; docker exec ai-delivery-assistant-db-1 psql -c "SELECT 'projects', COUNT(*) FROM projects UNION ALL SELECT 'meetings', COUNT(*) FROM meetings..."`
Constraints: Disk space via D: junction; Docker Desktop auto-update disabled; postgres:16 base image

## Decisions
- 2026-10-18 — план создан (миграция на глобальный шаблон v2); процесс живёт в `.dsh/AGENTS.md`, здесь — только состояние.
- 2026-10-20 — Docker Desktop на D:\Docker\wsl через NTFS-junction (Infra / Machine in ENVIRONMENT.md).
- 2026-10-20 — Dockerfile копирует providers/, services/, static/ + frontend-build stage (фикс ImportError при старте).
- 2026-10-20 — compose.yml использует postgres:16 (совпадает с inventory), schema.sql заменён реальным дампом из локального PG 18 (промаркированный \restrict закомментирован для совместимости psql 16).
- 2026-10-20 — tsc-check.sh удалён (scratch-файл).
- 2026-10-20 — Docker Desktop auto-update отключён (AutoDownloadUpdates=False, DisableUpdate=True) через settings-store.json, так как апдейт не влезал на диск C:.

## Learnings
- 2026-10-20 — Инфраструктура: Docker Desktop (WSL2) на внешнем накопителе D: (junction) — см. `ENVIRONMENT.md` (Infra / Machine).
- 2026-10-18 — работа feature/consolidation-review-queue (app.py, models.py, project_memory.py, project_overview.html) закончилась прямыми коммитами в main — дальше строго через ветки и PR.
- 2026-10-20 — Healthcheck postgres в compose требует готовность БД; схема инициализируется через schema.sql в initdb.d; при смене схемы нужно пересоздать том pgdata_ai.

## Next steps
1. Вычистить устаревшие feature-ветки (20+: feature/consolidation-*, feature/meeting-analysis-view, ui-tweaks, refactor-plan, …).
2. (Опционально) добавить интеграционные тесты для API endpoints.

## Archive
- ✅ Rewriting the Flask app as FastAPI + React (7110261)
- ✅ Security audit + GitHub Actions (ece6773); Dependabot + SECURITY.md (51bf4db)
- ✅ Type-checking fixes: models.py/api.py (7c2c035)
- ✅ План засеян при миграции на AGENT_PLAN.md (2026-10-18)
- ✅ 001 — Docker full-stack build + data migration (feature/001-docker-fullstack)