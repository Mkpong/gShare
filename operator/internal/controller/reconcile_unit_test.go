/*
Reconcile unit tests on the controller-runtime fake client (no envtest): idempotency, the
finalizer/deletion flow, requeue on error, and the Terminated-report retry.
*/
package controller

import (
	"context"
	"errors"
	"sync"
	"testing"

	corev1 "k8s.io/api/core/v1"
	netv1 "k8s.io/api/networking/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/apimachinery/pkg/util/validation/field"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"
	"sigs.k8s.io/controller-runtime/pkg/client/interceptor"

	gsharev1 "github.com/gshare/operator/api/v1"
	"github.com/gshare/operator/internal/podbuilder"
	"github.com/gshare/operator/internal/sot"
)

// fakeSoT records status callbacks; Report fails while failReport is set.
type fakeSoT struct {
	mu         sync.Mutex
	events     []sot.StatusEvent
	failReport error
}

func (f *fakeSoT) Report(_ context.Context, _ string, ev sot.StatusEvent) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.failReport != nil {
		return f.failReport
	}
	f.events = append(f.events, ev)
	return nil
}

func (f *fakeSoT) phases() []string {
	f.mu.Lock()
	defer f.mu.Unlock()
	out := make([]string, 0, len(f.events))
	for _, e := range f.events {
		out = append(out, e.Phase)
	}
	return out
}

func (f *fakeSoT) AuditOperator(context.Context, sot.AuditEvent) error  { return nil }
func (f *fakeSoT) UpsertGpuDevice(context.Context, sot.GpuDevice) error { return nil }
func (f *fakeSoT) UpsertNode(context.Context, sot.Node) error           { return nil }
func (f *fakeSoT) CordonedNodes(context.Context) ([]string, error)      { return nil, nil }
func (f *fakeSoT) DecommissioningNodes(context.Context) ([]string, error) {
	return nil, nil
}
func (f *fakeSoT) NodeDecommissioned(context.Context, string) error { return nil }
func (f *fakeSoT) ReportDrift(context.Context, string, int, int) error {
	return nil
}
func (f *fakeSoT) CreateNodeHealthEvent(_ context.Context, ev sot.NodeHealthEvent) (sot.NodeHealthEvent, error) {
	return ev, nil
}
func (f *fakeSoT) SyncVolumes(context.Context, []sot.VolumeObserved, []sot.SessionDisk, []sot.PoolCapacity) (sot.VolumeSyncResult, error) {
	return sot.VolumeSyncResult{}, nil
}

func testScheme(t *testing.T) *runtime.Scheme {
	t.Helper()
	s := runtime.NewScheme()
	if err := corev1.AddToScheme(s); err != nil {
		t.Fatal(err)
	}
	if err := netv1.AddToScheme(s); err != nil {
		t.Fatal(err)
	}
	if err := gsharev1.AddToScheme(s); err != nil {
		t.Fatal(err)
	}
	return s
}

func cpuSession(name string) *gsharev1.GShareSession {
	s := &gsharev1.GShareSession{}
	s.Name = name
	s.Namespace = "gshare-sessions"
	s.Spec = gsharev1.GShareSessionSpec{
		ClusterID: "clu_test", ResourceClass: "cpu", Image: "registry/base:latest",
		OfferingID: "off_cpu", ClusterMode: "single", Owner: "usr_test", Cpu: 1, MemGb: 1,
	}
	return s
}

type harness struct {
	c   client.Client
	r   *SessionReconciler
	sot *fakeSoT
	req ctrl.Request
}

func newHarness(t *testing.T, s *gsharev1.GShareSession, funcs interceptor.Funcs) *harness {
	t.Helper()
	scheme := testScheme(t)
	// The API server assigns a UID on create; the fake client does not. mapPhase treats an
	// empty UID as "no pod", so stamp one the way the server would.
	inner := funcs.Create
	funcs.Create = func(ctx context.Context, c client.WithWatch, obj client.Object, opts ...client.CreateOption) error {
		if obj.GetUID() == "" {
			obj.SetUID(types.UID("uid-" + obj.GetName()))
		}
		if inner != nil {
			return inner(ctx, c, obj, opts...)
		}
		return c.Create(ctx, obj, opts...)
	}
	c := fake.NewClientBuilder().
		WithScheme(scheme).
		WithStatusSubresource(&gsharev1.GShareSession{}).
		WithObjects(s).
		WithInterceptorFuncs(funcs).
		Build()
	rep := &fakeSoT{}
	r := &SessionReconciler{
		Client:    c,
		Scheme:    scheme,
		Builder:   &podbuilder.Builder{Namespace: s.Namespace},
		SoT:       rep,
		ClusterID: "clu_test",
	}
	return &harness{c: c, r: r, sot: rep, req: ctrl.Request{NamespacedName: client.ObjectKeyFromObject(s)}}
}

func (h *harness) reconcile(t *testing.T) ctrl.Result {
	t.Helper()
	res, err := h.r.Reconcile(context.Background(), h.req)
	if err != nil {
		t.Fatalf("reconcile: %v", err)
	}
	return res
}

func (h *harness) session(t *testing.T) *gsharev1.GShareSession {
	t.Helper()
	var s gsharev1.GShareSession
	if err := h.c.Get(context.Background(), h.req.NamespacedName, &s); err != nil {
		t.Fatalf("get session: %v", err)
	}
	return &s
}

// markPodRunning simulates the kubelet: the pod gets a UID, a node and phase Running.
func (h *harness) markPodRunning(t *testing.T, s *gsharev1.GShareSession) {
	t.Helper()
	var pod corev1.Pod
	if err := h.c.Get(context.Background(), podKey(s), &pod); err != nil {
		t.Fatalf("get pod: %v", err)
	}
	pod.Spec.NodeName = "node-a"
	if err := h.c.Update(context.Background(), &pod); err != nil {
		t.Fatalf("update pod: %v", err)
	}
	// Pods carry a status subresource in the fake client: the phase goes through Status().
	pod.Status.Phase = corev1.PodRunning
	pod.Status.ContainerStatuses = []corev1.ContainerStatus{{Name: "session", RestartCount: 0,
		State: corev1.ContainerState{Running: &corev1.ContainerStateRunning{}}}}
	if err := h.c.Status().Update(context.Background(), &pod); err != nil {
		t.Fatalf("update pod status: %v", err)
	}
}

func TestReconcileIsIdempotent(t *testing.T) {
	s := cpuSession("idem")
	h := newHarness(t, s, interceptor.Funcs{})

	h.reconcile(t)
	got := h.session(t)
	if !hasFinalizer(got) {
		t.Fatalf("first reconcile must add the finalizer, got %v", got.Finalizers)
	}
	// Children exist once.
	for _, key := range []client.ObjectKey{
		{Namespace: s.Namespace, Name: "ses-" + s.Name},
		{Namespace: s.Namespace, Name: "ses-" + s.Name + "-secret"},
	} {
		if err := h.c.Get(context.Background(), key, &corev1.Pod{}); err != nil && key.Name == "ses-"+s.Name {
			t.Fatalf("pod missing after first reconcile: %v", err)
		}
	}
	h.markPodRunning(t, s)

	h.reconcile(t) // observes Running -> status update + Running report
	after2 := h.session(t)
	if after2.Status.Phase != "Running" {
		t.Fatalf("expected phase Running, got %q", after2.Status.Phase)
	}
	var pod2 corev1.Pod
	if err := h.c.Get(context.Background(), podKey(s), &pod2); err != nil {
		t.Fatal(err)
	}

	res := h.reconcile(t) // nothing changed: heartbeat only, no writes
	after3 := h.session(t)
	if after3.ResourceVersion != after2.ResourceVersion {
		t.Fatalf("a no-change reconcile rewrote the session (rv %s -> %s)", after2.ResourceVersion, after3.ResourceVersion)
	}
	var pod3 corev1.Pod
	if err := h.c.Get(context.Background(), podKey(s), &pod3); err != nil {
		t.Fatal(err)
	}
	if pod3.ResourceVersion != pod2.ResourceVersion {
		t.Fatalf("a no-change reconcile rewrote the pod (rv %s -> %s)", pod2.ResourceVersion, pod3.ResourceVersion)
	}
	if res.RequeueAfter != heartbeatInterval {
		t.Fatalf("a live pod must be requeued at the heartbeat interval, got %v", res)
	}
	phases := h.sot.phases()
	if len(phases) < 2 || phases[len(phases)-1] != "Heartbeat" || phases[len(phases)-2] != "Running" {
		t.Fatalf("expected ... Running, Heartbeat; got %v", phases)
	}
	// Exactly one Running report across the three reconciles.
	running := 0
	for _, p := range phases {
		if p == "Running" {
			running++
		}
	}
	if running != 1 {
		t.Fatalf("Running must be reported once, got %d in %v", running, phases)
	}
}

func TestDeletionCleansChildrenReportsTerminatedAndReleasesTheFinalizer(t *testing.T) {
	s := cpuSession("del")
	h := newHarness(t, s, interceptor.Funcs{})
	h.reconcile(t)
	h.markPodRunning(t, s)
	h.reconcile(t)

	if err := h.c.Delete(context.Background(), h.session(t)); err != nil {
		t.Fatalf("delete: %v", err)
	}
	// The finalizer holds the object: it must still be there, now with a deletion timestamp.
	pending := h.session(t)
	if pending.DeletionTimestamp.IsZero() {
		t.Fatalf("expected a deletion timestamp while the finalizer is held")
	}

	h.reconcile(t)

	if err := h.c.Get(context.Background(), h.req.NamespacedName, &gsharev1.GShareSession{}); !apierrors.IsNotFound(err) {
		t.Fatalf("session must be gone once the finalizer is released, got err=%v", err)
	}
	for _, obj := range []client.Object{
		&corev1.Pod{}, &corev1.Service{}, &corev1.Secret{}, &netv1.Ingress{},
	} {
		name := "ses-" + s.Name
		switch obj.(type) {
		case *corev1.Secret:
			name += "-secret"
		case *netv1.Ingress:
			name += "-apps"
		}
		err := h.c.Get(context.Background(), client.ObjectKey{Namespace: s.Namespace, Name: name}, obj)
		if !apierrors.IsNotFound(err) {
			t.Fatalf("child %T %s must be deleted, got err=%v", obj, name, err)
		}
	}
	phases := h.sot.phases()
	if phases[len(phases)-1] != "Terminated" {
		t.Fatalf("deletion must report Terminated last, got %v", phases)
	}
	// Reconciling a deleted object is a no-op.
	h.reconcile(t)
}

func TestDeletionKeepsTheFinalizerWhileTheTerminatedReportFails(t *testing.T) {
	s := cpuSession("del-retry")
	h := newHarness(t, s, interceptor.Funcs{})
	h.reconcile(t)
	if err := h.c.Delete(context.Background(), h.session(t)); err != nil {
		t.Fatalf("delete: %v", err)
	}

	h.sot.failReport = errors.New("sot: POST /internal/sessions/x/status: status 503")
	_, err := h.r.Reconcile(context.Background(), h.req)
	if err == nil {
		t.Fatalf("a failed Terminated report must requeue (error), not drop the settlement")
	}
	held := h.session(t) // still present: the finalizer was kept
	if !hasFinalizer(held) {
		t.Fatalf("finalizer must be kept while the report fails, got %v", held.Finalizers)
	}

	h.sot.failReport = nil
	h.reconcile(t)
	if err := h.c.Get(context.Background(), h.req.NamespacedName, &gsharev1.GShareSession{}); !apierrors.IsNotFound(err) {
		t.Fatalf("session must be released once the report succeeds, got err=%v", err)
	}
	if p := h.sot.phases(); len(p) == 0 || p[len(p)-1] != "Terminated" {
		t.Fatalf("expected a Terminated report on retry, got %v", p)
	}
}

func TestTransientCreateErrorIsReturnedForRequeue(t *testing.T) {
	s := cpuSession("requeue")
	boom := errors.New("etcdserver: request timed out")
	h := newHarness(t, s, interceptor.Funcs{
		Create: func(ctx context.Context, c client.WithWatch, obj client.Object, opts ...client.CreateOption) error {
			if _, ok := obj.(*corev1.Pod); ok {
				return boom
			}
			return c.Create(ctx, obj, opts...)
		},
	})
	_, err := h.r.Reconcile(context.Background(), h.req)
	if !errors.Is(err, boom) {
		t.Fatalf("a transient create failure must be returned so controller-runtime requeues, got %v", err)
	}
	if p := h.sot.phases(); len(p) != 0 {
		t.Fatalf("no phase must be reported while the pod could not be created, got %v", p)
	}
}

func TestInvalidPodIsReportedAsErrorWithoutRequeue(t *testing.T) {
	s := cpuSession("invalid")
	h := newHarness(t, s, interceptor.Funcs{
		Create: func(ctx context.Context, c client.WithWatch, obj client.Object, opts ...client.CreateOption) error {
			if _, ok := obj.(*corev1.Pod); ok {
				return apierrors.NewInvalid(schema.GroupKind{Kind: "Pod"}, obj.GetName(),
					field.ErrorList{field.Invalid(field.NewPath("spec"), "x", "bad")})
			}
			return c.Create(ctx, obj, opts...)
		},
	})
	res, err := h.r.Reconcile(context.Background(), h.req)
	if err != nil || res.Requeue || res.RequeueAfter != 0 {
		t.Fatalf("an invalid pod never succeeds by retrying: expected no error/no requeue, got res=%v err=%v", res, err)
	}
	p := h.sot.phases()
	if len(p) != 1 || p[0] != "Error" {
		t.Fatalf("expected exactly one Error report, got %v", p)
	}
	if h.sot.events[0].Generation != h.session(t).Generation {
		t.Fatalf("the Error report must carry the CR generation")
	}
}

func hasFinalizer(s *gsharev1.GShareSession) bool {
	for _, f := range s.Finalizers {
		if f == finalizer {
			return true
		}
	}
	return false
}
