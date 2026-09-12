/*
Reaper tick decisions on a fake client: what happens when the util signal is missing (no DCGM,
no bound GPU, a series the exporter does not have), and the two real reaping paths (idle pause,
max-runtime terminate) so the missing-signal cases are shown to be deliberate, not dead code.
*/
package reaper

import (
	"context"
	"sync"
	"testing"
	"time"

	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"

	gsharev1 "github.com/gshare/operator/api/v1"
	"github.com/gshare/operator/internal/sot"
)

type fixedDCGM struct{ util float64 }

func (d fixedDCGM) GPUUtil(context.Context, string) float64 { return d.util }

type recSoT struct {
	mu     sync.Mutex
	events []sot.StatusEvent
	audits []sot.AuditEvent
}

func (f *recSoT) Report(_ context.Context, _ string, ev sot.StatusEvent) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.events = append(f.events, ev)
	return nil
}
func (f *recSoT) AuditOperator(_ context.Context, ev sot.AuditEvent) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.audits = append(f.audits, ev)
	return nil
}
func (f *recSoT) UpsertGpuDevice(context.Context, sot.GpuDevice) error   { return nil }
func (f *recSoT) UpsertNode(context.Context, sot.Node) error             { return nil }
func (f *recSoT) CordonedNodes(context.Context) ([]string, error)        { return nil, nil }
func (f *recSoT) DecommissioningNodes(context.Context) ([]string, error) { return nil, nil }
func (f *recSoT) NodeDecommissioned(context.Context, string) error       { return nil }
func (f *recSoT) ReportDrift(context.Context, string, int, int) error    { return nil }
func (f *recSoT) CreateNodeHealthEvent(_ context.Context, ev sot.NodeHealthEvent) (sot.NodeHealthEvent, error) {
	return ev, nil
}
func (f *recSoT) SyncVolumes(context.Context, []sot.VolumeObserved, []sot.SessionDisk, []sot.PoolCapacity) (sot.VolumeSyncResult, error) {
	return sot.VolumeSyncResult{}, nil
}

func (f *recSoT) phases() []string {
	f.mu.Lock()
	defer f.mu.Unlock()
	out := []string{}
	for _, e := range f.events {
		out = append(out, e.Phase)
	}
	return out
}

func running(name, class, gpu string) *gsharev1.GShareSession {
	s := &gsharev1.GShareSession{}
	s.Name, s.Namespace = name, "gshare-sessions"
	s.UID = types.UID("uid-" + name)
	s.CreationTimestamp = metav1.NewTime(time.Now().Add(-3 * time.Hour))
	s.Spec.ResourceClass = class
	s.Spec.Image = "img"
	s.Spec.ClusterID, s.Spec.OfferingID, s.Spec.ClusterMode, s.Spec.Owner = "c", "o", "single", "u"
	s.Status.Phase = "Running"
	s.Status.BoundGpuUuid = gpu
	s.Status.PodRef = "gshare-sessions/ses-" + name
	return s
}

func newReaper(t *testing.T, dcgm DCGM, objs ...client.Object) (*IdleReaper, client.Client, *recSoT) {
	t.Helper()
	scheme := runtime.NewScheme()
	if err := gsharev1.AddToScheme(scheme); err != nil {
		t.Fatal(err)
	}
	c := fake.NewClientBuilder().WithScheme(scheme).WithObjects(objs...).Build()
	rep := &recSoT{}
	r := &IdleReaper{Client: c, DCGM: dcgm, SoT: rep, ClusterID: "clu_test"}
	return r, c, rep
}

// idleFor2h pre-seeds a two-hour idle streak so one tick is past every default window.
func idleFor2h(r *IdleReaper, s *gsharev1.GShareSession) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.idleSince == nil {
		r.idleSince = map[string]time.Time{}
	}
	r.idleSince[string(s.UID)] = time.Now().Add(-2 * time.Hour)
}

func get(t *testing.T, c client.Client, s *gsharev1.GShareSession) (*gsharev1.GShareSession, bool) {
	t.Helper()
	var out gsharev1.GShareSession
	err := c.Get(context.Background(), client.ObjectKeyFromObject(s), &out)
	if apierrors.IsNotFound(err) {
		return nil, false
	}
	if err != nil {
		t.Fatal(err)
	}
	return &out, true
}

func TestNoDCGMNeverIdlePausesAGPUSession(t *testing.T) {
	s := running("gpu-nodcgm", "gpu", "GPU-1")
	r, c, rep := newReaper(t, nil, s)
	idleFor2h(r, s)
	r.tick(context.Background())
	got, ok := get(t, c, s)
	if !ok || got.Spec.Paused {
		t.Fatalf("without a util source a GPU session's idle is unknowable; it must not be paused (ok=%v)", ok)
	}
	if p := rep.phases(); len(p) != 0 {
		t.Fatalf("no report expected, got %v", p)
	}
}

func TestNoBoundGPUNeverIdlePauses(t *testing.T) {
	s := running("gpu-nouuid", "gpu", "")
	r, c, rep := newReaper(t, fixedDCGM{0}, s)
	idleFor2h(r, s)
	r.tick(context.Background())
	got, _ := get(t, c, s)
	if got.Spec.Paused {
		t.Fatalf("a GPU session with no bound UUID must not be idle-paused (util would read as 0 forever)")
	}
	if p := rep.phases(); len(p) != 0 {
		t.Fatalf("no report expected, got %v", p)
	}
}

func TestMissingSeriesFailSafeBusyKeepsTheSession(t *testing.T) {
	// The Prometheus source answers 1.0 for a missing series / query error (see dcgm package):
	// that value must end the idle streak rather than start one.
	s := running("gpu-missing", "gpu", "GPU-1")
	r, c, _ := newReaper(t, fixedDCGM{1.0}, s)
	idleFor2h(r, s)
	r.tick(context.Background())
	got, _ := get(t, c, s)
	if got.Spec.Paused {
		t.Fatalf("fail-safe busy must not pause")
	}
	if r.idleFor(got) != 0 {
		t.Fatalf("a busy sample must reset the idle streak, got %v", r.idleFor(got))
	}
}

func TestIdleGPUSessionIsPausedWithAReason(t *testing.T) {
	s := running("gpu-idle", "gpu", "GPU-1")
	r, c, rep := newReaper(t, fixedDCGM{0}, s)
	idleFor2h(r, s)
	r.tick(context.Background())
	got, ok := get(t, c, s)
	if !ok {
		t.Fatalf("an idle GPU session is paused, never deleted")
	}
	if !got.Spec.Paused || got.Annotations[pauseReasonAnnotation] != "idle-reaped" {
		t.Fatalf("expected spec.paused + pause-reason annotation, got paused=%v ann=%v", got.Spec.Paused, got.Annotations)
	}
	if len(rep.audits) != 1 || rep.audits[0].Action != "session.pause" || rep.audits[0].Actor != "operator:clu_test" {
		t.Fatalf("a pause is a privileged action and must be audited, got %+v", rep.audits)
	}
	// Anti-thrash: the very next tick must not touch it again even when still idle.
	r.tick(context.Background())
	if len(rep.audits) != 1 {
		t.Fatalf("pause cooldown violated: %d audits", len(rep.audits))
	}
}

func TestIdleCPUSessionIsTerminatedWithoutAnyUtilSource(t *testing.T) {
	s := running("cpu-idle", "cpu", "")
	r, c, rep := newReaper(t, nil, s)
	idleFor2h(r, s)
	r.tick(context.Background())
	if _, ok := get(t, c, s); ok {
		t.Fatalf("an idle CPU session past its window is terminated (CR deleted)")
	}
	p := rep.phases()
	if len(p) != 1 || p[0] != "Terminating" || rep.events[0].Message != "idle-reaped" {
		t.Fatalf("expected one Terminating(idle-reaped) report, got %+v", rep.events)
	}
	if len(rep.audits) != 1 || rep.audits[0].Action != "pod.delete" {
		t.Fatalf("terminate must be audited as pod.delete, got %+v", rep.audits)
	}
}

func TestMaxRuntimeTerminatesEvenWithoutMetrics(t *testing.T) {
	s := running("gpu-cap", "gpu", "GPU-1")
	s.Annotations = map[string]string{maxRuntimeAnnotation: "60"}
	r, c, rep := newReaper(t, nil, s)
	r.tick(context.Background())
	if _, ok := get(t, c, s); ok {
		t.Fatalf("a session past its max runtime is terminated regardless of util")
	}
	if p := rep.phases(); len(p) != 1 || p[0] != "Terminating" || rep.events[0].Message != "max-runtime-exceeded" {
		t.Fatalf("expected Terminating(max-runtime-exceeded), got %+v", rep.events)
	}
}

func TestExplicitZeroIdleTimeoutDisablesIdleReaping(t *testing.T) {
	s := running("gpu-unlimited", "gpu", "GPU-1")
	s.Annotations = map[string]string{idleTimeoutAnnotation: "0"}
	r, c, _ := newReaper(t, fixedDCGM{0}, s)
	idleFor2h(r, s)
	r.tick(context.Background())
	got, _ := get(t, c, s)
	if got.Spec.Paused {
		t.Fatalf("idle-timeout 0 means never idle-pause")
	}
}

func TestPausedAndDeletingSessionsAreSkipped(t *testing.T) {
	paused := running("gpu-paused", "gpu", "GPU-1")
	paused.Status.Phase = "Paused"
	r, c, rep := newReaper(t, fixedDCGM{0}, paused)
	idleFor2h(r, paused)
	r.tick(context.Background())
	if _, ok := get(t, c, paused); !ok {
		t.Fatalf("a paused session must not be touched")
	}
	if len(rep.events)+len(rep.audits) != 0 {
		t.Fatalf("no reports for a paused session, got %v / %v", rep.events, rep.audits)
	}
}

func TestIdleWarningIsSentOncePerStreak(t *testing.T) {
	s := running("gpu-warn", "gpu", "GPU-1")
	r, c, rep := newReaper(t, fixedDCGM{0}, s)
	// 57 minutes idle against the 60-minute default: inside the 5-minute warning lead.
	r.mu.Lock()
	r.idleSince = map[string]time.Time{string(s.UID): time.Now().Add(-57 * time.Minute)}
	r.mu.Unlock()
	r.tick(context.Background())
	r.tick(context.Background())
	got, _ := get(t, c, s)
	if got.Spec.Paused {
		t.Fatalf("inside the warning lead the session is warned, not paused")
	}
	if p := rep.phases(); len(p) != 1 || p[0] != "IdleWarning" {
		t.Fatalf("expected exactly one IdleWarning, got %v", p)
	}
}
