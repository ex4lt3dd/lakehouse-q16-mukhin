# Практическая №1: Lakehouse, вариант 4 — TPC-H Q16

**ФИО:** Мухин Глеб Дмитриевич. **Масштаб:** `sf1`.

Репозиторий для сдачи: [ex4lt3dd/lakehouse-q16-mukhin](https://github.com/ex4lt3dd/lakehouse-q16-mukhin).

Отчёт — [отчет.md](отчет.md), результаты запросов и замеров — в [results](results/).

## Стек и поток данных

```text
TPC-H sf1 → Trino → Bronze → Silver → Gold → Superset
                  │          │         │
                  └── Lakekeeper REST Catalog ── PostgreSQL
                              │
                    Silo / MinIO S3 API
                    bronze / silver / gold
```

Стек: Trino 476, PostgreSQL 17, Lakekeeper, Silo и Apache Superset 4.1.2. Silo — S3-совместимый форк MinIO. У каждого слоя отдельный бакет, warehouse и каталог Trino. Контейнеры и тома используют префикс `mukhin-q16`.

## Запуск на Windows

Нужны работающий Docker Desktop с Linux containers, PowerShell 5.1 или 7 и Python 3.10+. Python-скрипты используют стандартную библиотеку; устанавливать пакеты на хост не требуется.

Из папки репозитория:

```powershell
# Полный первый запуск: сервисы, SQL, бенчмарк, evolution, time travel, BI.
./scripts/run.ps1 -Python python
```

Если Python не добавлен в PATH, укажите путь к нему через `-Python`.

`start.ps1` генерирует локальный `.env` со случайными значениями. Существующий `.env` сохраняется. Для повторного запуска только сервисов используйте:

```powershell
./scripts/start.ps1 -Python python
docker compose ps
python -X utf8 scripts/lab.py validate
```

`run.ps1` выполняет первый запуск на пустых томах. Если Bronze уже существует, загрузка останавливается. Для проверки готового проекта достаточно `start.ps1`, `lab.py validate` и `setup_superset.py`.

Новый запуск обновляет файлы в `results`. Результат Q16 сохраняется, а время замеров и snapshot ID могут отличаться.

## Адреса и доступ

| Сервис | Адрес | Учётные данные |
| --- | --- | --- |
| S3 API | http://localhost:9000 | `S3_ACCESS_KEY`, `S3_SECRET_KEY` из `.env` |
| S3 console | http://localhost:19001 | те же |
| Lakekeeper | http://localhost:8181/ui/ | локальный учебный режим без авторизации |
| Trino | http://localhost:8080 | user `gleb`, пароль пустой |
| Superset | http://localhost:8088 | user `admin`, `SUPERSET_ADMIN_PASSWORD` из `.env` |
| Dashboard Q16 | http://localhost:8088/superset/dashboard/mukhin-q16/ | вход в Superset |

Порт 9001 на хосте был занят, поэтому S3 console опубликована на 19001. PostgreSQL доступен только внутри Docker network. Host-порты привязаны к `127.0.0.1`: стек предназначен для локальной практической.

Для DBeaver: connection **Trino**, host `localhost`, port `8080`, user `gleb`, пароль пустой; JDBC URL `jdbc:trino://localhost:8080/bronze/lakehouse`. SQL находится в папке `sql`; скрипты выполняют его через REST API Trino.

## SQL и результаты

| Файл / папка | Назначение |
| --- | --- |
| `docker-compose.yml`, `catalog/`, `trino/`, `superset/` | запускаемые конфиги |
| `sql/01-bronze.sql` | три исходные таблицы с проекцией нужных колонок |
| `sql/02-silver.sql` | допустимые поставщики и отфильтрованные связи деталь–поставщик |
| `sql/03-gold.sql` | агрегат Q16 и явная сортировка при чтении |
| `sql/q16.sql` | исходный Q16, адаптированный к Bronze |
| `sql/04-time-travel.sql` | восстановление из snapshot |
| `scripts/lab.py` | provisioning, SQL, benchmark, проверки, evolution/time travel |
| `scripts/setup_superset.py` | подключения BI, запросы Bronze и дашборд Gold |
| `results/queries.jsonl` | SQL, query IDs и метрики Trino |
| `results/q16-gold.csv` | полный отсортированный результат Q16 |
| `results/table-metrics.json` | число строк, файлов, байты и схемы таблиц |
| `results/benchmark.json`, `benchmark-runs.csv` | методика и каждый прогон GZIP/ZSTD |
| `results/schema-evolution.json`, `time-travel.json` | результаты schema evolution и time travel |
| `results/validation.json`, `superset.json` | сравнение с TPC-H и ответы BI |
| `results/reproducibility.json` | проверка запуска чистой копии |

Бенчмарк создаёт одинаковые таблицы в `bronze.bench_gzip` и `bronze.bench_zstd` и выполняет Q16 с join, фильтрами и `count(DISTINCT)`. Основной Bronze сохраняется.

Размер — сумма `file_size_in_bytes` из Iceberg `$files`, без metadata и старых snapshots. В отчёте используется MiB: `bytes / 1024²`. Время берётся из `elapsedTimeMillis` Trino. Замеры выполняются с прогретым OS cache.

Для остановки с сохранением данных:

```powershell
docker compose stop
```

`.env` и Docker volumes остаются локально. В репозитории находятся код, отчёт и результаты.

## Документация

- [Iceberg connector Trino 476](https://github.com/trinodb/trino/blob/476/docs/src/main/sphinx/connector/iceberg.md).
- [S3 configuration Trino 476](https://github.com/trinodb/trino/blob/476/docs/src/main/sphinx/object-storage/file-system-s3.md).
- [Lakekeeper bootstrap](https://github.com/lakekeeper/lakekeeper/blob/main/docs/docs/bootstrap.md).
- [Superset: Trino](https://superset.apache.org/user-docs/databases/supported/trino/).

Конфиги рассчитаны на Trino 476 и используют `fs.native-s3.enabled=true`.
