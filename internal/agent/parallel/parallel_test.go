package parallel

import (
	"context"
	"errors"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/idev/internal/agent/delegate"
)

// The batch rules these tests pin are fanout.py's, restated for this host:
// cap bounds concurrency, every task returns a result, one task's panic or
// error is that task's outcome and not the wave's.

func TestBatchRespectsCap(t *testing.T) {
	var running, peak int32
	var mu sync.Mutex
	capSeen := 0
	_ = peak
	tasks := make([]Task, 10)
	for i := range tasks {
		tasks[i] = Task{Executor: "idev-fixture", Brief: "b"}
	}
	run := func(ctx context.Context, t Task) delegate.Report {
		cur := atomic.AddInt32(&running, 1)
		mu.Lock()
		if int(cur) > capSeen {
			capSeen = int(cur)
		}
		mu.Unlock()
		time.Sleep(30 * time.Millisecond)
		atomic.AddInt32(&running, -1)
		return delegate.Report{Status: "PASS"}
	}
	results := Batch(context.Background(), 3, tasks, run, nil)
	if capSeen > 3 {
		t.Errorf("peak concurrency %d over cap 3", capSeen)
	}
	if len(results) != 10 {
		t.Fatalf("results: %d", len(results))
	}
	for i, r := range results {
		if r.Err != nil || r.Report.Status != "PASS" {
			t.Errorf("result %d: %+v err=%v", i, r.Report, r.Err)
		}
	}
}

func TestBatchIsolatesFailures(t *testing.T) {
	tasks := []Task{
		{Executor: "ok", Brief: "1"},
		{Executor: "boom", Brief: "2"},
		{Executor: "ok", Brief: "3"},
	}
	run := func(ctx context.Context, t Task) delegate.Report {
		if t.Executor == "boom" {
			panic("executor exploded")
		}
		return delegate.Report{Status: "PASS"}
	}
	var errCount int
	results := Batch(context.Background(), 2, tasks, run, func(t Task, err error) { errCount++ })
	if len(results) != 3 {
		t.Fatalf("results: %d", len(results))
	}
	if results[0].Err != nil || results[0].Report.Status != "PASS" {
		t.Errorf("task 0 damaged by neighbor failure: %+v %v", results[0].Report, results[0].Err)
	}
	if results[2].Err != nil || results[2].Report.Status != "PASS" {
		t.Errorf("task 2 damaged by neighbor failure: %+v %v", results[2].Report, results[2].Err)
	}
	if results[1].Err == nil {
		t.Error("panic must surface as that task's error")
	}
	if errCount != 1 {
		t.Errorf("onError calls: %d", errCount)
	}
}

func TestHardCapClamps(t *testing.T) {
	var peak int32
	tasks := make([]Task, 12)
	for i := range tasks {
		tasks[i] = Task{Executor: "x"}
	}
	var peakSeen int32
	run := func(ctx context.Context, t Task) delegate.Report {
		cur := atomic.AddInt32(&peak, 1)
		for {
			old := atomic.LoadInt32(&peakSeen)
			if cur <= old || atomic.CompareAndSwapInt32(&peakSeen, old, cur) {
				break
			}
		}
		time.Sleep(20 * time.Millisecond)
		atomic.AddInt32(&peak, -1)
		return delegate.Report{Status: "PASS"}
	}
	Batch(context.Background(), 100, tasks, run, nil) // 100 clamps to HardCap
	if got := atomic.LoadInt32(&peakSeen); got > int32(HardCap) {
		t.Errorf("peak %d over hard cap %d", got, HardCap)
	}
}

func TestEmptyBatch(t *testing.T) {
	results := Batch(context.Background(), 4, nil, func(ctx context.Context, t Task) delegate.Report {
		return delegate.Report{}
	}, nil)
	if len(results) != 0 {
		t.Errorf("empty batch: %d", len(results))
	}
	var e error = errPanic{v: 1}
	if !errors.Is(e, e) {
		t.Fatal("sanity")
	}
}
