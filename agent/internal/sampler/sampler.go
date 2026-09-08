package sampler

import (
	"context"
	"log/slog"
	"sync"
	"time"
)

// Pod is the little the sampler needs to know about a session pod.
type Pod struct {
	Name      string // pod name
	UID       string
	QOSClass  string
	SessionCR string // gshare.io/session label: the CR name the control plane maps back to a session
}

// Sample is one reading of one session, already converted to the units the console shows.
type Sample struct {
	Session  string  `json:"session"`   // CR name
	At       float64 `json:"at"`        // unix seconds, fractional
	CPUCores float64 `json:"cpu_cores"` // cores used over the interval since the previous sample
	MemBytes uint64  `json:"mem_bytes"`
}

// Lister returns the session pods currently assigned to this node.
type Lister func(context.Context) ([]Pod, error)

// Sink receives each batch of samples.
type Sink func(context.Context, []Sample) error

type prev struct {
	usec uint64
	at   time.Time
}

// Run samples every `interval` until ctx is done, handing each batch to sink.
//
// CPU is a rate, so the first reading of a pod only seeds the counter — a session appears in the
// stream one interval after it starts. Pods that vanish mid-loop are dropped silently: a pod
// ending is the normal case, not an error worth logging every second.
func Run(ctx context.Context, interval time.Duration, list Lister, sink Sink, log *slog.Logger) {
	var mu sync.Mutex
	last := map[string]prev{}    // pod UID -> previous CPU counter
	paths := map[string]string{} // pod UID -> resolved cgroup path

	tick := time.NewTicker(interval)
	defer tick.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case now := <-tick.C:
			pods, err := list(ctx)
			if err != nil {
				log.Warn("list session pods", "err", err)
				continue
			}
			live := make(map[string]struct{}, len(pods))
			batch := make([]Sample, 0, len(pods))
			for _, p := range pods {
				live[p.UID] = struct{}{}
				mu.Lock()
				dir, ok := paths[p.UID]
				mu.Unlock()
				if !ok {
					d, err := PodPath(p.UID, p.QOSClass)
					if err != nil {
						continue // the pod may not have its cgroup yet
					}
					dir = d
					mu.Lock()
					paths[p.UID] = d
					mu.Unlock()
				}
				r, err := Read(dir)
				if err != nil {
					continue
				}
				mu.Lock()
				pv, seen := last[p.UID]
				last[p.UID] = prev{usec: r.CPUUsageUsec, at: now}
				mu.Unlock()
				if !seen {
					continue // seed only: a rate needs two points
				}
				cores, ok := Rate(pv.usec, r.CPUUsageUsec, now.Sub(pv.at).Seconds())
				if !ok {
					continue
				}
				batch = append(batch, Sample{
					Session:  p.SessionCR,
					At:       float64(now.UnixNano()) / 1e9,
					CPUCores: cores,
					MemBytes: r.MemBytes,
				})
			}
			// Forget pods that are gone, so the maps cannot grow without bound on a busy node.
			mu.Lock()
			for uid := range last {
				if _, ok := live[uid]; !ok {
					delete(last, uid)
					delete(paths, uid)
				}
			}
			mu.Unlock()
			if len(batch) == 0 {
				continue
			}
			if err := sink(ctx, batch); err != nil {
				log.Warn("push samples", "n", len(batch), "err", err)
			}
		}
	}
}

// Rate converts two cumulative CPU readings into cores used over the interval between them.
//
// It reports ok=false rather than a number when the pair cannot describe an interval: a
// non-positive elapsed time (the clock moved), or a counter that went backwards, which means the
// cgroup was recreated under the same pod. Either would otherwise draw a spike that never happened.
func Rate(prevUsec, curUsec uint64, elapsedSec float64) (float64, bool) {
	if elapsedSec <= 0 || curUsec < prevUsec {
		return 0, false
	}
	return float64(curUsec-prevUsec) / 1e6 / elapsedSec, true
}
