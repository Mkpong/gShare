package sampler

import (
	"context"
	"io"
	"log/slog"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func writeCgroup(t *testing.T, dir string, usageUsec, memBytes string) {
	t.Helper()
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatal(err)
	}
	stat := "usage_usec " + usageUsec + "\nuser_usec 1\nsystem_usec 1\n"
	if err := os.WriteFile(filepath.Join(dir, "cpu.stat"), []byte(stat), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "memory.current"), []byte(memBytes+"\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "memory.max"), []byte("max\n"), 0o644); err != nil {
		t.Fatal(err)
	}
}

func TestPodPathHandlesEveryQoSClass(t *testing.T) {
	root := t.TempDir()
	Root = root
	t.Cleanup(func() { Root = "/sys/fs/cgroup" })

	guaranteed := filepath.Join(root, "kubepods.slice", "kubepods-podaa_bb.slice")
	burstable := filepath.Join(root, "kubepods.slice", "kubepods-burstable.slice", "kubepods-burstable-podcc_dd.slice")
	for _, d := range []string{guaranteed, burstable} {
		if err := os.MkdirAll(d, 0o755); err != nil {
			t.Fatal(err)
		}
	}
	if got, err := PodPath("aa-bb", "Guaranteed"); err != nil || got != guaranteed {
		t.Fatalf("guaranteed: got %q err %v", got, err)
	}
	if got, err := PodPath("cc-dd", "Burstable"); err != nil || got != burstable {
		t.Fatalf("burstable: got %q err %v", got, err)
	}
	if _, err := PodPath("no-such", "Guaranteed"); err == nil {
		t.Fatal("a missing cgroup must be an error, not an empty path")
	}
}

func TestReadParsesTheCountersAndTreatsMaxAsNoLimit(t *testing.T) {
	dir := t.TempDir()
	writeCgroup(t, dir, "1500000", "147189760")
	r, err := Read(dir)
	if err != nil {
		t.Fatal(err)
	}
	if r.CPUUsageUsec != 1_500_000 || r.MemBytes != 147_189_760 {
		t.Fatalf("got %+v", r)
	}
	if r.MemMaxBytes != 0 {
		t.Fatalf(`memory.max "max" must read as 0 (no limit), got %d`, r.MemMaxBytes)
	}
}

// The first reading of a pod only seeds the counter; the second is the first real rate. Getting
// this wrong would report a session's entire lifetime of CPU as one interval's usage.
func TestFirstSampleSeedsAndSecondReportsTheRate(t *testing.T) {
	root := t.TempDir()
	Root = root
	t.Cleanup(func() { Root = "/sys/fs/cgroup" })
	dir := filepath.Join(root, "kubepods.slice", "kubepods-podpod_1.slice")
	writeCgroup(t, dir, "1000000", "1000")

	pods := []Pod{{Name: "p", UID: "pod-1", QOSClass: "Guaranteed", SessionCR: "ses-abc"}}
	list := func(context.Context) ([]Pod, error) { return pods, nil }

	got := make(chan []Sample, 4)
	sink := func(_ context.Context, s []Sample) error { got <- s; return nil }

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go Run(ctx, 20*time.Millisecond, list, sink, slog.New(slog.NewTextHandler(io.Discard, nil)))

	// after the seed, advance the counter by half a second of CPU
	time.Sleep(30 * time.Millisecond)
	writeCgroup(t, dir, "1500000", "2000")

	select {
	case batch := <-got:
		if len(batch) != 1 || batch[0].Session != "ses-abc" {
			t.Fatalf("unexpected batch %+v", batch)
		}
		if batch[0].CPUCores <= 0 {
			t.Fatalf("a rate was expected, got %+v", batch[0])
		}
		if batch[0].MemBytes != 2000 {
			t.Fatalf("memory should be the latest reading, got %d", batch[0].MemBytes)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("no batch arrived; the seed sample was probably emitted as a rate")
	}
}

// A counter that goes backwards means the cgroup was recreated under the same pod, and a clock
// that does not advance gives no interval at all. Either would draw a spike that never happened.
func TestRateRefusesImpossibleIntervals(t *testing.T) {
	if got, ok := Rate(1_000_000, 1_500_000, 0.5); !ok || got < 0.99 || got > 1.01 {
		t.Fatalf("half a second of CPU in half a second is one core, got %v ok=%v", got, ok)
	}
	if _, ok := Rate(9_000_000, 5, 1); ok {
		t.Fatal("a backwards counter must be refused, not wrapped")
	}
	if _, ok := Rate(1, 2, 0); ok {
		t.Fatal("a zero interval must be refused, not divided by")
	}
	if got, ok := Rate(1_000, 1_000, 1); !ok || got != 0 {
		t.Fatalf("an idle pod is a real zero, got %v ok=%v", got, ok)
	}
}
