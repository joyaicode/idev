-- +goose Up
-- I-1 is one write lease per overlapping path set. Empty paths cover the
-- feature. Globs such as ** are decided in leaseRepo.Issue; this trigger is
-- the backstop for raw inserts: empty paths, identical paths, and literal
-- prefixes still refuse a second active write lease.
DROP INDEX IF EXISTS leases_single_writer_feature;
DROP INDEX IF EXISTS leases_single_writer_run;

DROP TRIGGER IF EXISTS leases_write_paths_conflict;

-- +goose StatementBegin
CREATE TRIGGER leases_write_paths_conflict
BEFORE INSERT ON leases
WHEN NEW.purpose = 'write' AND NEW.status = 'active'
BEGIN
  SELECT RAISE(ABORT, 'leases_single_writer_feature')
  WHERE EXISTS (
    SELECT 1 FROM leases AS held
    WHERE held.status = 'active'
      AND held.purpose = 'write'
      AND (
        (NEW.feature_id IS NOT NULL AND held.feature_id = NEW.feature_id)
        OR (NEW.feature_id IS NULL AND held.feature_id IS NULL AND held.run_id = NEW.run_id)
      )
      AND (
        json_array_length(COALESCE(held.write_paths_json, '[]')) = 0
        OR json_array_length(COALESCE(NEW.write_paths_json, '[]')) = 0
        OR EXISTS (
          SELECT 1
          FROM json_each(held.write_paths_json) AS h, json_each(NEW.write_paths_json) AS n
          WHERE h.value = n.value
             OR h.value || '/' = substr(n.value, 1, length(h.value) + 1)
             OR n.value || '/' = substr(h.value, 1, length(n.value) + 1)
        )
      )
  );
END;
-- +goose StatementEnd

-- +goose Down
DROP TRIGGER IF EXISTS leases_write_paths_conflict;
CREATE UNIQUE INDEX leases_single_writer_feature ON leases(feature_id)
    WHERE status = 'active' AND purpose = 'write' AND feature_id IS NOT NULL;
CREATE UNIQUE INDEX leases_single_writer_run ON leases(run_id)
    WHERE status = 'active' AND purpose = 'write';
