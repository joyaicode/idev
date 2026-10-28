package auditsvc

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"time"

	"github.com/idev/internal/domain/audit"
	"github.com/idev/internal/ports"
)

// ExportLine is one JSONL row of an audit export. Hash is included so an
// offline reader can verify the chain without the store.
type ExportLine struct {
	Seq      int64          `json:"seq"`
	At       time.Time      `json:"at"`
	Action   audit.Action   `json:"action"`
	Actor    audit.Actor    `json:"actor"`
	RunID    string         `json:"run_id,omitempty"`
	StepID   string         `json:"step_id,omitempty"`
	Feature  string         `json:"feature,omitempty"`
	Subject  string         `json:"subject,omitempty"`
	Detail   map[string]any `json:"detail,omitempty"`
	PrevHash string         `json:"prev_hash"`
	Hash     string         `json:"hash"`
}

// Export writes the audit chain as JSONL. When runID is non-empty only
// events for that run are emitted (still in seq order). The walk is a
// read; a missing or partial write by the caller cannot roll back the
// decisions already committed (E5.4: export is not on the transaction).
func (s Service) Export(ctx context.Context, runID string, w io.Writer) (int, error) {
	if s.Store == nil {
		return 0, fmt.Errorf("auditsvc: Export without a store")
	}
	const page = 100
	from := int64(1)
	count := 0
	enc := json.NewEncoder(w)
	enc.SetEscapeHTML(false)
	for {
		var events []audit.Event
		err := s.Store.InTx(ctx, func(tx ports.Tx) error {
			var err error
			events, err = tx.Audit().Range(ctx, from, page)
			return err
		})
		if err != nil {
			return count, err
		}
		if len(events) == 0 {
			return count, nil
		}
		for _, ev := range events {
			if runID != "" && ev.RunID != runID {
				continue
			}
			line := ExportLine{
				Seq: ev.Seq, At: ev.At, Action: ev.Action, Actor: ev.Actor,
				RunID: ev.RunID, StepID: ev.StepID, Feature: ev.Feature,
				Subject: ev.Subject, Detail: ev.Detail,
				PrevHash: string(ev.PrevHash), Hash: string(ev.Hash),
			}
			if err := enc.Encode(line); err != nil {
				return count, fmt.Errorf("auditsvc: writing export line seq %d: %w", ev.Seq, err)
			}
			count++
		}
		from = events[len(events)-1].Seq + 1
		if len(events) < page {
			return count, nil
		}
	}
}
