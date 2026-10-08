# Практическая №1: Lakehouse, вариант 4 — TPC-H Q16

**ФИО:** Мухин Глеб Дмитриевич. **Масштаб:** `sf1`.

Репозиторий для сдачи: [ex4lt3dd/lakehouse-q16-mukhin](https://github.com/ex4lt3dd/lakehouse-q16-mukhin).

Основной документ для сдачи — [отчёт](отчет.md). Все числа в нём получены на реально запущенном Docker-стеке; исходные результаты находятся в [results](results/).

## Стек и поток данных

```text
TPC-H sf1 → Trino → Bronze → Silver → Gold → Superset
                  │          │         │
                  └── Lakekeeper REST Catalog ── PostgreSQL
                              │
                    Silo / MinIO S3 API
                    bronze / silver / gold
```

Используются Trino 476, PostgreSQL 17, Lakekeeper, Silo (совместимый форк MinIO из поправки к гайду) и Apache Superset 4.1.2. Каждый слой имеет отдельный бакет, warehouse и каталог Trino. Имена контейнеров и томов начинаются с `mukhin-q16`, что отделяет эту работу от других проектов.

## Запуск на Windows

Нужны работающий Docker Desktop с Linux containers, PowerShell и Python 3.10+. Python-скрипты используют стандартную библиотеку; устанавливать пакеты на хост не требуется.

Из папки репозитория:

```powershell
# Полный первый запуск: сервисы, SQL, бенчмарк, evolution, time travel, BI.
./scripts/run.ps1 -Python python
```

На компьютере, где выполнена работа, использовался Python из bundled runtime Codex, переданный через параметр `-Python`. Можно указать абсолютный путь к любому рабочему Python 3.10+.

`start.ps1` генерирует локальный `.env` со случайными значениями. Существующий `.env` сохраняется. Для повторного запуска только сервисов используйте:

```powershell
./scripts/start.ps1 -Python python
docker compose ps
python -X utf8 scripts/lab.py validate
```

Загрузка данных `build` предназначена для пустого проекта: она останавливается, если Bronze уже создан, чтобы не перезаписать данные. Аналогично benchmark/evolution не следует повторять поверх уже созданных демонстрационных объектов. Для нового полного эксперимента используйте отдельный Docker Compose project и свободные host-порты, а не удаляйте существующие тома.

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

Для DBeaver: новый connection **Trino**, host `localhost`, port `8080`, user `gleb`, пароль пустой; JDBC URL `jdbc:trino://localhost:8080/bronze/lakehouse`. SQL из папки `sql` можно выполнять в DBeaver. Фактически работа выполнена через REST API и консольные скрипты, поэтому дополнительные ручные действия в DBeaver не требуются.

## SQL и результаты

| Файл / папка | Назначение |
| --- | --- |
| `docker-compose.yml`, `catalog/`, `trino/`, `superset/` | запускаемые конфиги |
| `sql/01-bronze.sql` | три исходные таблицы с проекцией нужных колонок |
| `sql/02-silver.sql` | допустимые поставщики и отфильтрованные связи деталь–поставщик |
| `sql/03-gold.sql` | агрегат Q16 и явная сортировка при чтении |
| `sql/q16.sql` | исходный Q16, адаптированный к Bronze |
| `sql/04-time-travel.sql` | восстановление с фактическим snapshot ID |
| `scripts/lab.py` | provisioning, SQL, benchmark, проверки, evolution/time travel |
| `scripts/setup_superset.py` | BI connections, реальные запросы Bronze, dataset/chart/dashboard Gold |
| `results/queries.jsonl` | SQL, query IDs и метрики Trino |
| `results/q16-gold.csv` | полный отсортированный результат Q16 |
| `results/table-metrics.json` | число строк, файлов, байты и схемы таблиц |
| `results/benchmark.json`, `benchmark-runs.csv` | методика и каждый прогон GZIP/ZSTD |
| `results/schema-evolution.json`, `time-travel.json` | доказательства экспериментов |
| `results/validation.json`, `superset.json` | сравнение с TPC-H и ответы BI |

Бенчмарк физически материализует одинаковые таблицы в `bronze.bench_gzip` и `bronze.bench_zstd`. Основной Bronze остаётся неизменным. Это не сравнение времени чтения готового Gold: каждый прогон выполняет полный Q16 с join, фильтрами и `count(DISTINCT)` на Bronze.

Размер считается по сумме `file_size_in_bytes` из Iceberg `$files`; это активные файлы данных текущего snapshot, без JSON/Avro metadata и старых snapshots. В отчёте используется MiB (`bytes / 1024²`). Время — `elapsedTimeMillis`, измеренное сервером Trino, без старта CLI. Измерения проводятся с прогретым OS cache; сброс Windows/WSL cache не заявляется.

Для остановки с сохранением данных:

```powershell
docker compose stop
```

`.env`, Docker volumes и бинарные данные не включаются в Git. В репозитории остаются код, заполненный отчёт и подтверждающие результаты.

## Документация

- [Iceberg connector Trino 476](https://github.com/trinodb/trino/blob/476/docs/src/main/sphinx/connector/iceberg.md).
- [S3 configuration Trino 476](https://github.com/trinodb/trino/blob/476/docs/src/main/sphinx/object-storage/file-system-s3.md).
- [Lakekeeper bootstrap](https://github.com/lakekeeper/lakekeeper/blob/main/docs/docs/bootstrap.md).
- [Superset: Trino](https://superset.apache.org/user-docs/databases/supported/trino/).

В предоставленных гайдах использованы настройки Trino 476, поэтому здесь сохранена эта версия и `fs.native-s3.enabled=true`. В новых версиях имя S3-активатора может отличаться; автоматически менять его без обновления Trino нельзя.
