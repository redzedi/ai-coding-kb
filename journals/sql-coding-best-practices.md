## SQL coding best practices

- **MySQL composite index column order**: Place most selective + frequently-filtered-together columns adjacent. `(page_id, is_delete, widget_id)` beats `(page_id, widget_id, is_delete)` when most queries filter `page_id + is_delete` together — leftmost prefix matching stops at first skipped column.
- 
- **MySQL online index creation**: InnoDB supports `ALGORITHM=INPLACE, LOCK=NONE` by default since 5.6 — no table locks. Use explicit syntax in production to fail-fast if online isn't possible. Main risk is IOPS budget on RDS, not locking.
