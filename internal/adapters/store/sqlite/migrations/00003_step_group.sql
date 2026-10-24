-- +goose Up
-- A projected run keeps the wave the Python driver opened. run.yaml stays
-- the source of truth; these columns are what a loaded run uses for Open.
ALTER TABLE steps ADD COLUMN group_id TEXT NOT NULL DEFAULT '';
ALTER TABLE steps ADD COLUMN writes_json TEXT NOT NULL DEFAULT '[]';

-- +goose Down
ALTER TABLE steps DROP COLUMN writes_json;
ALTER TABLE steps DROP COLUMN group_id;
