-- Реальный snapshot из этого запуска; для новой загрузки получите свой ID.
SELECT snapshot_id FROM silver.lakehouse."eligible_supplier$snapshots"
ORDER BY committed_at DESC;
SELECT count(*) FROM silver.lakehouse.eligible_supplier FOR VERSION AS OF 3187102991790105271;
ALTER TABLE silver.lakehouse.eligible_supplier EXECUTE rollback_to_snapshot(3187102991790105271);
SELECT count(*) FROM silver.lakehouse.eligible_supplier;
