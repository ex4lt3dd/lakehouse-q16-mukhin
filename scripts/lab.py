"""Воспроизводимый Q16: REST API Trino, проверки и реальные измерения."""
import argparse
import csv
import hashlib
from http.client import RemoteDisconnected
import json
import os
from pathlib import Path
import statistics
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)


def env_values():
    return dict(line.split("=", 1) for line in (ROOT / ".env").read_text().splitlines()
                if line and not line.startswith("#"))


def http_json(url, body=None, headers=None, method=None):
    payload = None if body is None else json.dumps(body).encode()
    # Docker host-порты привязаны к IPv4; localhost сначала пробует недоступный ::1.
    url = url.replace("http://localhost:", "http://127.0.0.1:")
    request = Request(url, data=payload, headers={"Content-Type": "application/json", **(headers or {})}, method=method)
    try:
        with urlopen(request, timeout=120) as response:
            data = response.read()
            return (json.loads(data) if data else None), response.headers
    except HTTPError as error:
        message = error.read().decode(errors="replace")
        # Структурированный запрос может включать credentials; не печатаем его.
        raise RuntimeError(f"HTTP {error.code} {url}: {message}") from error


class Trino:
    def __init__(self):
        self.session = {}

    def query(self, sql, label="query"):
        started = time.perf_counter()
        headers = {"X-Trino-User": "gleb", "X-Trino-Source": "mukhin-q16-lab"}
        if self.session:
            headers["X-Trino-Session"] = ",".join(f"{k}={v}" for k, v in self.session.items())
        request = Request("http://127.0.0.1:8080/v1/statement", data=sql.encode(), headers=headers)
        rows, columns = [], []
        with urlopen(request, timeout=120) as response:
            page = json.load(response)
            for value in response.headers.get_all("X-Trino-Set-Session", []):
                key, val = value.split("=", 1)
                self.session[key] = val
        while True:
            if "error" in page:
                raise RuntimeError(f"{label}: {page['error']['message']}")
            if "columns" in page:
                columns = [column["name"] for column in page["columns"]]
            rows.extend(page.get("data", []))
            if "nextUri" not in page:
                break
            page, _ = http_json(page["nextUri"], headers=headers)
        record = {"label": label, "query_id": page["id"], "sql": sql,
                  "stats": page["stats"], "client_seconds": round(time.perf_counter() - started, 6),
                  "rows_returned": len(rows)}
        with (RESULTS / "queries.jsonl").open("a", encoding="utf-8") as output:
            output.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"{label}: {page['id']} | {page['stats'].get('elapsedTimeMillis')} ms | {len(rows)} rows", flush=True)
        return {"columns": columns, "rows": rows, **record}

    def scalar(self, sql, label="scalar"):
        return self.query(sql, label)["rows"][0][0]


def save(name, value):
    (RESULTS / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def save_csv(name, result):
    with (RESULTS / name).open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(result["columns"])
        writer.writerows(result["rows"])


def provision():
    for _ in range(120):
        try:
            http_json("http://localhost:8181/health")
            break
        except (URLError, RuntimeError, RemoteDisconnected):
            time.sleep(2)
    else:
        raise RuntimeError("Lakekeeper не готов за 240 секунд")
    info, _ = http_json("http://localhost:8181/management/v1/info")
    if not info.get("bootstrapped", False):
        http_json("http://localhost:8181/management/v1/bootstrap", {"accept-terms-of-use": True})
    existing, _ = http_json("http://localhost:8181/management/v1/warehouse?project-id=00000000-0000-0000-0000-000000000000")
    names = {warehouse.get("warehouse-name", warehouse.get("name")) for warehouse in existing.get("warehouses", [])}
    values = env_values()
    for layer in ("bronze", "silver", "gold"):
        if layer not in names:
            body = {"warehouse-name": layer, "project-id": "00000000-0000-0000-0000-000000000000",
                    "storage-profile": {"type": "s3", "bucket": layer, "key-prefix": "",
                                        "endpoint": "http://minio:9000", "region": "us-east-1",
                                        "path-style-access": True, "flavor": "s3-compat", "sts-enabled": False},
                    "storage-credential": {"type": "s3", "credential-type": "access-key",
                                           "access-key-id": values["S3_ACCESS_KEY"], "secret-access-key": values["S3_SECRET_KEY"]}}
            result, _ = http_json("http://localhost:8181/management/v1/warehouse", body)
            print(f"Warehouse {layer}: created", flush=True)
    existing, _ = http_json("http://localhost:8181/management/v1/warehouse?project-id=00000000-0000-0000-0000-000000000000")
    save("warehouses.json", existing)
    for _ in range(120):
        try:
            info, _ = http_json("http://localhost:8080/v1/info")
            if not info.get("starting", True):
                break
        except (URLError, RuntimeError, RemoteDisconnected):
            pass
        time.sleep(2)
    else:
        raise RuntimeError("Trino не готов за 240 секунд")
    Trino().query("SHOW CATALOGS", "catalogs")


def build():
    trino = Trino()
    tables = trino.scalar("SELECT count(*) FROM bronze.information_schema.tables WHERE table_schema='lakehouse'", "existing_bronze")
    if tables:
        raise RuntimeError("Bronze уже создан: повторная загрузка остановлена, чтобы сохранить данные")
    for filename in ("01-bronze.sql", "02-silver.sql", "03-gold.sql"):
        text = (ROOT / "sql" / filename).read_text(encoding="utf-8")
        for index, statement in enumerate(text.split(";")):
            if statement.strip():
                trino.query(statement.strip(), f"{filename}:{index + 1}")
    validate(trino)


def validate(trino=None):
    trino = trino or Trino()
    q16 = (ROOT / "sql/q16.sql").read_text().strip().rstrip(";")
    reference = trino.query(q16.replace("bronze.lakehouse", "tpch.sf1"), "q16_tpch_reference")
    bronze = trino.query(q16, "q16_bronze")
    gold = trino.query("SELECT brand,type,size,supplier_cnt FROM gold.lakehouse.q16_supplier_counts ORDER BY supplier_cnt DESC,brand,type,size", "q16_gold")
    assert reference["rows"] == bronze["rows"] == gold["rows"], "Результаты Q16 различаются"
    checks = []
    for table, key in (("part", "partkey"), ("supplier", "suppkey")):
        result = trino.query(f"SELECT count(*),count(DISTINCT {key}),count_if({key} IS NULL) FROM bronze.lakehouse.{table}", f"quality_{table}")
        count, distinct, nulls = result["rows"][0]
        assert count == distinct and nulls == 0
        checks.append({"table": table, "rows": count, "unique_keys": distinct, "null_keys": nulls})
    ps = trino.query("SELECT count(*) AS rows,count(DISTINCT ROW(partkey,suppkey)) AS unique_pairs,count_if(partkey IS NULL OR suppkey IS NULL) AS null_keys FROM bronze.lakehouse.partsupp", "quality_partsupp")
    count, distinct, nulls = ps["rows"][0]
    assert count == distinct and nulls == 0
    assert trino.scalar("SELECT count(*) FROM bronze.lakehouse.supplier WHERE comment IS NULL", "null_supplier_comments") == 0
    invalid = trino.scalar("SELECT count(*) FROM silver.lakehouse.part_supplier ps LEFT JOIN bronze.lakehouse.supplier s ON ps.suppkey=s.suppkey WHERE s.suppkey IS NULL OR s.comment LIKE '%Customer%Complaints%'", "silver_exclusions")
    assert invalid == 0
    save_csv("q16-gold.csv", gold)
    save("validation.json", {"equal_tpch_bronze_gold": True, "gold_rows": len(gold["rows"]),
                             "sha256": hashlib.sha256(json.dumps(gold["rows"]).encode()).hexdigest(),
                             "keys": checks, "partsupp": ps["rows"], "invalid_silver_suppliers": invalid})


def measure():
    trino = Trino()
    metrics = []
    for catalog, table in (("bronze", "part"), ("bronze", "partsupp"), ("bronze", "supplier"),
                           ("silver", "eligible_supplier"), ("silver", "part_supplier"), ("gold", "q16_supplier_counts")):
        name = f"{catalog}.lakehouse.{table}"
        rows = trino.scalar(f"SELECT count(*) FROM {name}", f"count_{catalog}_{table}")
        files = trino.query(f'SELECT count(*) AS files,coalesce(sum(file_size_in_bytes),0) AS bytes FROM {catalog}.lakehouse."{table}$files"', f"size_{catalog}_{table}")
        columns = trino.query(f"SHOW COLUMNS FROM {name}", f"columns_{catalog}_{table}")
        metrics.append({"table": name, "rows": rows, "files": files["rows"][0][0], "bytes": files["rows"][0][1],
                        "MiB": round(files["rows"][0][1] / 1024 ** 2, 6), "columns": columns["rows"]})
    save("table-metrics.json", metrics)


def benchmark(measure_only=False):
    trino = Trino()
    source = {"part": "partkey,brand,type,size", "partsupp": "partkey,suppkey", "supplier": "suppkey,comment"}
    sizes, writes = {}, []
    if measure_only:
        writes = json.loads((RESULTS / "benchmark.json").read_text(encoding="utf-8"))["writes"]
    q16 = (ROOT / "sql/q16.sql").read_text().strip().rstrip(";")
    reference = trino.query(q16, "benchmark_reference")["rows"]
    for codec in ("GZIP", "ZSTD"):
        schema = "bench_" + codec.lower()
        trino.query(f"CREATE SCHEMA IF NOT EXISTS bronze.{schema}", f"schema_{schema}")
        trino.query(f"SET SESSION bronze.compression_codec='{codec}'", f"codec_{codec}")
        size = 0
        for table, columns in source.items():
            if not measure_only:
                result = trino.query(f"CREATE TABLE bronze.{schema}.{table} WITH(format='PARQUET') AS SELECT {columns} FROM tpch.sf1.{table}", f"write_{codec}_{table}")
                writes.append({"codec": codec, "table": table, "query_id": result["query_id"], "elapsed_ms": result["stats"]["elapsedTimeMillis"]})
            size += trino.scalar(f'SELECT sum(file_size_in_bytes) FROM bronze.{schema}."{table}$files"', f"bench_size_{codec}_{table}")
        sizes[codec] = size
        warm = trino.query(q16.replace("bronze.lakehouse", f"bronze.{schema}"), f"warmup_{codec}")
        assert warm["rows"] == reference
    runs = []
    for iteration in range(1, 6):
        order = ("GZIP", "ZSTD") if iteration % 2 else ("ZSTD", "GZIP")
        for codec in order:
            result = trino.query(q16.replace("bronze.lakehouse", "bronze.bench_" + codec.lower()), f"benchmark_{codec}_{iteration}")
            assert result["rows"] == reference
            runs.append({"codec": codec, "iteration": iteration, "query_id": result["query_id"],
                         "elapsed_ms": result["stats"]["elapsedTimeMillis"], "client_seconds": result["client_seconds"]})
    summary = [{"codec": codec, "bytes": sizes[codec], "MiB": sizes[codec] / 1024 ** 2,
                "median_ms": statistics.median(r["elapsed_ms"] for r in runs if r["codec"] == codec),
                "min_ms": min(r["elapsed_ms"] for r in runs if r["codec"] == codec),
                "max_ms": max(r["elapsed_ms"] for r in runs if r["codec"] == codec)} for codec in ("GZIP", "ZSTD")]
    save("benchmark.json", {"method": "sf1; identical projections; PARQUET; no partitions; 1 warmup + 5 alternating measured Q16 per codec; elapsedTimeMillis from Trino REST; warm OS cache; no concurrent load", "runs": runs, "writes": writes, "summary": summary})
    save_csv("benchmark-runs.csv", {"columns": list(runs[0]), "rows": [list(r.values()) for r in runs]})


def evolution():
    trino = Trino()
    name = "silver.lakehouse.part_supplier"
    file_sql = 'SELECT file_path,file_size_in_bytes FROM silver.lakehouse."part_supplier$files" ORDER BY file_path'
    before = trino.query(file_sql, "schema_files_before")["rows"]
    trino.query(f"ALTER TABLE {name} ADD COLUMN quality_note varchar", "add_column")
    trino.query(f"ALTER TABLE {name} RENAME COLUMN quality_note TO data_note", "rename_column")
    row = trino.query(f"SELECT count(*) AS rows,count_if(data_note IS NULL) AS null_new_column FROM {name}", "new_column_nulls")["rows"][0]
    after = trino.query(file_sql, "schema_files_after")["rows"]
    assert before == after and row[0] == row[1]
    trino.query(f"SHOW COLUMNS FROM {name}", "schema_after")
    save("schema-evolution.json", {"rows": row[0], "null_new_column": row[1], "data_files_unchanged": before == after,
                                   "added": "quality_note", "renamed": "data_note"})


def travel():
    trino = Trino()
    name = "silver.lakehouse.eligible_supplier"
    before = trino.scalar(f"SELECT count(*) FROM {name}", "snapshot_before_count")
    snapshot = trino.scalar('SELECT snapshot_id FROM silver.lakehouse."eligible_supplier$snapshots" ORDER BY committed_at DESC LIMIT 1', "snapshot_original")
    key = trino.scalar(f"SELECT min(suppkey) FROM {name}", "snapshot_deleted_key")
    trino.query(f"DELETE FROM {name} WHERE suppkey={key}", "snapshot_delete")
    deleted = trino.scalar(f"SELECT count(*) FROM {name}", "snapshot_after_delete_count")
    historical = trino.scalar(f"SELECT count(*) FROM {name} FOR VERSION AS OF {snapshot}", "time_travel_count")
    trino.query(f"ALTER TABLE {name} EXECUTE rollback_to_snapshot({snapshot})", "rollback_to_snapshot")
    restored = trino.scalar(f"SELECT count(*) FROM {name}", "snapshot_restored_count")
    assert before == historical == restored and deleted == before - 1
    sql = f'''-- Реальный snapshot из этого запуска; для новой загрузки получите свой ID.
SELECT snapshot_id FROM silver.lakehouse."eligible_supplier$snapshots"
ORDER BY committed_at DESC;
SELECT count(*) FROM {name} FOR VERSION AS OF {snapshot};
ALTER TABLE {name} EXECUTE rollback_to_snapshot({snapshot});
SELECT count(*) FROM {name};
'''
    (ROOT / "sql/04-time-travel.sql").write_text(sql, encoding="utf-8")
    save("time-travel.json", {"snapshot_id": snapshot, "deleted_suppkey": key, "before": before,
                              "after_delete": deleted, "historical": historical, "restored": restored})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("provision", "build", "validate", "measure", "benchmark", "evolution", "travel"))
    parser.add_argument("--measure-only", action="store_true", help="Повторить измерения на уже созданных benchmark-таблицах")
    args = parser.parse_args()
    if args.action == "benchmark":
        benchmark(measure_only=args.measure_only)
    else:
        if args.measure_only:
            parser.error("--measure-only применяется только к benchmark")
        globals()[args.action]()
