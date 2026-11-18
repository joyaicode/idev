// Package parallel runs delegations concurrently, with the same discipline
// the kernel's fanout.py already fixed: bounded concurrency, write tools
// serialized by the lease service anyway, and a QUEUED tail instead of an
// unbounded wave. A batch of reports is a set of results, never a vote —
// one executor's conclusion is not another's evidence, the kernel's own
// rule, and it holds double when both ran in parallel.
package parallel

import (
	"context"
	"sync"

	"github.com/idev/internal/agent/delegate"
)

// DefaultCap matches fanout.py: a wave runs four at a time.
const DefaultCap = 4

// HardCap matches fanout.py's absolute ceiling: eight. The rest queue.
const HardCap = 8

// Task is one delegation in a batch.
type Task struct {
	Executor string
	Brief     string
}

// Batch runs every task under the cap. Tasks beyond the cap are QUEUED:
// they run in later waves, they are never dropped, and the kernel's
// "先完成的一片不取消其余" holds because every result carries its own
// status, not a shared one.
func Batch(ctx context.Context, cap int, tasks []Task, run func(ctx context.Context, t Task) delegate.Report, onError func(t Task, err error)) []Result {
	if cap <= 0 {
		cap = DefaultCap
	}
	if cap > HardCap {
		cap = HardCap
	}
	var mu sync.Mutex
	results := make([]Result, len(tasks))
	sem := make(chan struct{}, cap)
	var wg sync.WaitGroup
	for i, t := range tasks {
		wg.Add(1)
		go func(i int, t Task) {
			defer wg.Done()
			sem <- struct{}{}
			defer func() { <-sem }()
			rep, err := safeRun(ctx, t, run)
			mu.Lock()
			defer mu.Unlock()
			results[i] = Result{Task: t, Report: rep, Err: err}
			if err != nil && onError != nil {
				onError(t, err)
			}
		}(i, t)
	}
	wg.Wait()
	return results
}

func safeRun(ctx context.Context, t Task, run func(ctx context.Context, t Task) delegate.Report) (rep delegate.Report, err error) {
	defer func() {
		// A panic in one delegation must not take the batch down with
		// it; it becomes that task's error and the wave continues.
		if r := recover(); r != nil {
			err = errPanic{r}
		}
	}()
	return run(ctx, t), nil
}

type errPanic struct{ v any }

func (e errPanic) Error() string { return "parallel: delegation panicked" }

// Result is one task's outcome. Err set means no report; the caller
// treats it as one task's failure, not the batch's.
type Result struct {
	Task   Task
	Report delegate.Report
	Err    error
}
