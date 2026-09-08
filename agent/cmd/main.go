// gshare-agent — a per-node sampler that gives each session a one-second view of its own CPU and
// memory.
//
// It runs as a DaemonSet, watches only the session pods the kubelet placed on its own node, reads
// their cgroup v2 counters directly, and pushes batches to the control plane. The metrics pipeline
// (Prometheus + cAdvisor) stays as it is and remains the source for GPU, host and historical
// series; this path exists because cAdvisor's own ~10 s aggregation puts a floor under how fresh
// a scraped reading can be, and "did my job start using the GPU yet" is a question people ask at
// human latency.
package main

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/fields"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"

	"github.com/gshare/agent/internal/sampler"
)

func env(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func main() {
	log := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))

	node := os.Getenv("NODE_NAME")
	if node == "" {
		log.Error("NODE_NAME is required (downward API: spec.nodeName)")
		os.Exit(1)
	}
	base := env("GSHARE_API_URL", "http://gshare-api.gshare-system.svc:8080")
	tokenFile := env("INTERNAL_JWT_TOKEN_FILE", "/var/run/gshare/internal-jwt")
	ns := env("GSHARE_SESSION_NAMESPACE", "gshare-sessions")
	if root := os.Getenv("GSHARE_CGROUP_ROOT"); root != "" {
		sampler.Root = root
	}
	ms, err := strconv.Atoi(env("GSHARE_SAMPLE_INTERVAL_MS", "1000"))
	if err != nil || ms < 100 {
		// Below 100 ms the reading is dominated by the read itself, and the ingest rate stops
		// being worth what it costs the control plane.
		log.Warn("invalid GSHARE_SAMPLE_INTERVAL_MS, using 1000", "value", os.Getenv("GSHARE_SAMPLE_INTERVAL_MS"))
		ms = 1000
	}

	cfg, err := rest.InClusterConfig()
	if err != nil {
		log.Error("in-cluster config", "err", err)
		os.Exit(1)
	}
	cs, err := kubernetes.NewForConfig(cfg)
	if err != nil {
		log.Error("kubernetes client", "err", err)
		os.Exit(1)
	}

	// Only this node's session pods: the field selector keeps the API server from sending the
	// agent the whole fleet on every tick.
	selector := fields.OneTermEqualSelector("spec.nodeName", node).String()
	list := func(ctx context.Context) ([]sampler.Pod, error) {
		pods, err := cs.CoreV1().Pods(ns).List(ctx, metav1.ListOptions{
			FieldSelector: selector,
			LabelSelector: "gshare.io/session",
		})
		if err != nil {
			return nil, err
		}
		out := make([]sampler.Pod, 0, len(pods.Items))
		for i := range pods.Items {
			p := &pods.Items[i]
			if p.Status.Phase != "Running" {
				continue
			}
			out = append(out, sampler.Pod{
				Name:      p.Name,
				UID:       string(p.UID),
				QOSClass:  string(p.Status.QOSClass),
				SessionCR: p.Labels["gshare.io/session"],
			})
		}
		return out, nil
	}

	pusher := sampler.NewPusher(base, tokenFile, node)
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	log.Info("gshare-agent starting", "node", node, "interval_ms", ms, "api", base, "namespace", ns)
	sampler.Run(ctx, time.Duration(ms)*time.Millisecond, list, pusher.Push, log)
	log.Info("gshare-agent stopped")
}
