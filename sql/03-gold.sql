SET SESSION gold.compression_codec = 'ZSTD';
CREATE TABLE gold.lakehouse.q16_supplier_counts WITH (format = 'PARQUET') AS
SELECT brand, type, size, count(DISTINCT suppkey) AS supplier_cnt
FROM silver.lakehouse.part_supplier
GROUP BY brand, type, size;

SELECT brand, type, size, supplier_cnt
FROM gold.lakehouse.q16_supplier_counts
ORDER BY supplier_cnt DESC, brand, type, size;
