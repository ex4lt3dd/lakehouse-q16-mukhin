CREATE SCHEMA IF NOT EXISTS bronze.lakehouse;
CREATE SCHEMA IF NOT EXISTS silver.lakehouse;
CREATE SCHEMA IF NOT EXISTS gold.lakehouse;

SET SESSION bronze.compression_codec = 'ZSTD';
CREATE TABLE bronze.lakehouse.part WITH (format = 'PARQUET') AS
SELECT partkey, brand, type, size FROM tpch.sf1.part;
CREATE TABLE bronze.lakehouse.partsupp WITH (format = 'PARQUET') AS
SELECT partkey, suppkey FROM tpch.sf1.partsupp;
CREATE TABLE bronze.lakehouse.supplier WITH (format = 'PARQUET') AS
SELECT suppkey, comment FROM tpch.sf1.supplier;
