"""Подключение BI к Bronze/Gold, SQL Lab и витрина Q16 через API Superset."""
import http.cookiejar
import json
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener

from lab import ROOT, env_values, save

BASE = "http://127.0.0.1:8088"
opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
headers = {"Content-Type": "application/json", "Referer": BASE + "/"}


def api(path, payload=None, method=None):
    body = json.dumps(payload).encode() if payload is not None else None
    req = Request(BASE + path, data=body, headers=headers, method=method)
    try:
        with opener.open(req, timeout=180) as response:
            content = response.read()
            return json.loads(content) if content else None
    except HTTPError as error:
        raise RuntimeError(f"Superset {error.code} {path}: {error.read().decode(errors='replace')}") from error


def main():
    for _ in range(120):
        try:
            with opener.open(BASE + "/health", timeout=5) as response:
                if response.status == 200:
                    break
        except (HTTPError, URLError, TimeoutError):
            pass
        time.sleep(2)
    else:
        raise RuntimeError("Superset не готов за 240 секунд")
    login = api("/api/v1/security/login", {"username": "admin", "password": env_values()["SUPERSET_ADMIN_PASSWORD"],
                                           "provider": "db", "refresh": True})
    headers["Authorization"] = "Bearer " + login["access_token"]
    headers["X-CSRFToken"] = api("/api/v1/security/csrf_token/")["result"]
    databases = api("/api/v1/database/")["result"]
    db_ids = {}
    for layer in ("bronze", "gold"):
        name = "Lakehouse " + layer.capitalize()
        existing = next((d for d in databases if d["database_name"] == name), None)
        if existing:
            db_ids[layer] = existing["id"]
        else:
            created = api("/api/v1/database/", {"database_name": name, "sqlalchemy_uri": f"trino://gleb@trino:8080/{layer}",
                                              "expose_in_sqllab": True, "allow_run_async": False, "allow_dml": False})
            db_ids[layer] = created["id"]
        print(f"Superset database {name}: {db_ids[layer]}", flush=True)
    bronze_sql = "SELECT 'part' AS table_name,count(*) AS row_count FROM bronze.lakehouse.part UNION ALL SELECT 'partsupp',count(*) FROM bronze.lakehouse.partsupp UNION ALL SELECT 'supplier',count(*) FROM bronze.lakehouse.supplier"
    bronze_result = api("/api/v1/sqllab/execute/", {"database_id": db_ids["bronze"], "schema": "lakehouse", "sql": bronze_sql,
                                                "runAsync": False, "queryLimit": 1000, "client_id": uuid.uuid4().hex[:10]})
    assert bronze_result["status"] == "success", bronze_result
    sample = api("/api/v1/sqllab/execute/", {"database_id": db_ids["bronze"], "schema": "lakehouse",
                                         "sql": "SELECT partkey,brand,type,size FROM bronze.lakehouse.part ORDER BY partkey LIMIT 10",
                                         "runAsync": False, "queryLimit": 1000, "client_id": uuid.uuid4().hex[:10]})
    assert sample["status"] == "success", sample
    datasets = api("/api/v1/dataset/")["result"]
    existing = next((d for d in datasets if d["table_name"] == "q16_supplier_counts"), None)
    if existing:
        dataset_id = existing["id"]
    else:
        dataset = api("/api/v1/dataset/", {"database": db_ids["gold"], "schema": "lakehouse", "table_name": "q16_supplier_counts"})
        dataset_id = dataset["id"]
    charts = api("/api/v1/chart/")["result"]
    title = "Q16: поставщики по бренду, типу и размеру"
    existing = next((c for c in charts if c["slice_name"] == title), None)
    params = {"datasource": f"{dataset_id}__table", "viz_type": "table", "query_mode": "raw",
              "all_columns": ["brand", "type", "size", "supplier_cnt"], "row_limit": 50000,
              "order_by_cols": [json.dumps(["supplier_cnt", False]), json.dumps(["brand", True]),
                                json.dumps(["type", True]), json.dumps(["size", True])],
              "table_timestamp_format": "smart_date", "page_length": 20, "include_search": True}
    if existing:
        chart_id = existing["id"]
        api(f"/api/v1/chart/{chart_id}", {"params": json.dumps(params, ensure_ascii=False), "query_context_generation": True}, method="PUT")
    else:
        chart_id = api("/api/v1/chart/", {"slice_name": title, "viz_type": "table", "datasource_id": dataset_id,
                                         "datasource_type": "table", "params": json.dumps(params, ensure_ascii=False),
                                         "query_context_generation": True})["id"]
    dashboards = api("/api/v1/dashboard/")["result"]
    existing = next((d for d in dashboards if d["slug"] == "mukhin-q16"), None)
    if existing:
        dashboard_id = existing["id"]
    else:
        dashboard_id = api("/api/v1/dashboard/", {"dashboard_title": "Практическая №1 — Мухин Глеб Дмитриевич — Q16",
                                                 "slug": "mukhin-q16", "published": True})["id"]
    positions = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {"id": "ROOT_ID", "type": "ROOT", "children": ["GRID_ID"]},
        "GRID_ID": {"id": "GRID_ID", "type": "GRID", "children": ["ROW-Q16"], "parents": ["ROOT_ID"]},
        "HEADER_ID": {"id": "HEADER_ID", "type": "HEADER", "meta": {"text": "Практическая №1 — Q16"}},
        "ROW-Q16": {"id": "ROW-Q16", "type": "ROW", "children": ["CHART-Q16"], "parents": ["ROOT_ID", "GRID_ID"],
                    "meta": {"background": "BACKGROUND_TRANSPARENT"}},
        "CHART-Q16": {"id": "CHART-Q16", "type": "CHART", "children": [], "parents": ["ROOT_ID", "GRID_ID", "ROW-Q16"],
                      "meta": {"chartId": chart_id, "width": 12, "height": 80, "sliceName": title}}
    }
    api(f"/api/v1/dashboard/{dashboard_id}", {"position_json": json.dumps(positions, ensure_ascii=False),
                                             "json_metadata": json.dumps({"refresh_frequency": 0, "timed_refresh_immune_slices": []})}, method="PUT")
    chart_data = api("/api/v1/chart/data", {"datasource": {"id": dataset_id, "type": "table"},
                                          "queries": [{"columns": ["brand", "type", "size", "supplier_cnt"],
                                                       "metrics": [], "row_limit": 50000,
                                                       "orderby": [["supplier_cnt", False], ["brand", True], ["type", True], ["size", True]],
                                                       "time_range": "No filter"}],
                                          "result_format": "json", "result_type": "full"})
    gold_data = chart_data["result"][0]["data"]
    import csv
    with (ROOT / "results/q16-gold.csv").open(encoding="utf-8", newline="") as stream:
        expected = list(csv.DictReader(stream))
    assert len(gold_data) == len(expected)
    actual_rows = [(r["brand"], r["type"], int(r["size"]), int(r["supplier_cnt"])) for r in gold_data]
    expected_rows = [(r["brand"], r["type"], int(r["size"]), int(r["supplier_cnt"])) for r in expected]
    assert actual_rows == expected_rows, "Ответ BI отличается от Gold"
    save("superset.json", {"database_ids": db_ids, "dataset_id": dataset_id, "chart_id": chart_id,
                           "dashboard_id": dashboard_id, "dashboard_url": BASE + "/superset/dashboard/mukhin-q16/",
                           "bronze_sql": bronze_sql, "bronze_counts": bronze_result["data"], "bronze_sample": sample["data"],
                           "gold_rows_via_chart_api": len(gold_data), "gold_equals_trino_csv": True})
    print("Bronze query succeeded; Gold dashboard: " + BASE + "/superset/dashboard/mukhin-q16/", flush=True)


if __name__ == "__main__":
    main()
