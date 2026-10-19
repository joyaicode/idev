-- +goose Up
-- Which files a gate's digest covers. The domain keeps only the digest; the
-- local CLI needs the paths so `approve` can recompute it from the content as
-- it is when the person answers, not as it was when the agent asked.
CREATE TABLE gate_subjects (
    gate_id         TEXT    PRIMARY KEY REFERENCES gates(id),
    root            TEXT    NOT NULL,
    paths_json      TEXT    NOT NULL
) STRICT;

-- +goose Down
DROP TABLE IF EXISTS gate_subjects;
