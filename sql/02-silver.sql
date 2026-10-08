SET SESSION silver.compression_codec = 'ZSTD';

CREATE TABLE silver.lakehouse.eligible_supplier WITH (format = 'PARQUET') AS
SELECT suppkey FROM bronze.lakehouse.supplier
WHERE suppkey IS NOT NULL AND comment NOT LIKE '%Customer%Complaints%';

CREATE TABLE silver.lakehouse.part_supplier WITH (format = 'PARQUET') AS
SELECT p.partkey, ps.suppkey, p.brand, p.type, p.size
FROM bronze.lakehouse.part AS p
JOIN bronze.lakehouse.partsupp AS ps ON p.partkey = ps.partkey
JOIN silver.lakehouse.eligible_supplier AS s ON ps.suppkey = s.suppkey
WHERE p.brand <> 'Brand#45'
  AND p.type NOT LIKE 'MEDIUM POLISHED%'
  AND p.size IN (49, 14, 23, 45, 19, 3, 36, 9);
