package volumes

import (
	"context"
	"testing"

	corev1 "k8s.io/api/core/v1"
	storagev1 "k8s.io/api/storage/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/kubernetes/scheme"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"

	"github.com/gshare/operator/internal/podbuilder"
	"github.com/gshare/operator/internal/sot"
)

type fakeSoT struct {
	got      []sot.VolumeObserved
	sessions []sot.SessionDisk
	pools    []sot.PoolCapacity
	called   bool
	answer   sot.VolumeSyncResult
}

func (f *fakeSoT) Report(context.Context, string, sot.StatusEvent) error  { return nil }
func (f *fakeSoT) AuditOperator(context.Context, sot.AuditEvent) error    { return nil }
func (f *fakeSoT) UpsertGpuDevice(context.Context, sot.GpuDevice) error   { return nil }
func (f *fakeSoT) UpsertNode(context.Context, sot.Node) error             { return nil }
func (f *fakeSoT) CordonedNodes(context.Context) ([]string, error)        { return nil, nil }
func (f *fakeSoT) DecommissioningNodes(context.Context) ([]string, error) { return nil, nil }
func (f *fakeSoT) NodeDecommissioned(context.Context, string) error       { return nil }
func (f *fakeSoT) ReportDrift(context.Context, string, int, int) error    { return nil }
func (f *fakeSoT) CreateNodeHealthEvent(_ context.Context, ev sot.NodeHealthEvent) (sot.NodeHealthEvent, error) {
	return ev, nil
}
func (f *fakeSoT) SyncVolumes(_ context.Context, v []sot.VolumeObserved, sess []sot.SessionDisk, pools []sot.PoolCapacity) (sot.VolumeSyncResult, error) {
	f.pools = pools
	f.called = true
	f.got = v
	f.sessions = sess
	return f.answer, nil
}

func pvc(name, id string, gb int) *corev1.PersistentVolumeClaim {
	return &corev1.PersistentVolumeClaim{
		ObjectMeta: metav1.ObjectMeta{
			Namespace:   "gshare-sessions",
			Name:        name,
			Labels:      map[string]string{podbuilder.VolumeLabel: name},
			Annotations: map[string]string{podbuilder.VolumeIDAnnotation: id},
		},
		Spec: corev1.PersistentVolumeClaimSpec{
			Resources: corev1.VolumeResourceRequirements{Requests: corev1.ResourceList{
				corev1.ResourceStorage: resource.MustParse(resource.NewQuantity(int64(gb)<<30, resource.BinarySI).String()),
			}},
		},
	}
}

func podUsing(name, node, claim string) *corev1.Pod {
	return &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{Namespace: "gshare-sessions", Name: name},
		Spec: corev1.PodSpec{NodeName: node, Volumes: []corev1.Volume{{
			Name: "d", VolumeSource: corev1.VolumeSource{PersistentVolumeClaim: &corev1.PersistentVolumeClaimVolumeSource{ClaimName: claim}},
		}}},
		Status: corev1.PodStatus{Phase: corev1.PodRunning},
	}
}

// sessionPod builds a session pod the way podbuilder does: name "ses-"+crName, the CR name on
// the gshare.io/session label, and the scratch disk as the container's ephemeral-storage limit
// (0 = no limit set). claim "" mounts no volume.
func sessionPod(crName, node, claim string, ephemeralLimitGi int) *corev1.Pod {
	p := &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Namespace: "gshare-sessions",
			Name:      "ses-" + crName,
			Labels:    map[string]string{"gshare.io/session": crName},
		},
		Spec:   corev1.PodSpec{NodeName: node},
		Status: corev1.PodStatus{Phase: corev1.PodRunning},
	}
	if claim != "" {
		p.Spec.Volumes = []corev1.Volume{{
			Name: "d", VolumeSource: corev1.VolumeSource{PersistentVolumeClaim: &corev1.PersistentVolumeClaimVolumeSource{ClaimName: claim}},
		}}
	}
	if ephemeralLimitGi > 0 {
		p.Spec.Containers = []corev1.Container{{
			Name: "session",
			Resources: corev1.ResourceRequirements{Limits: corev1.ResourceList{
				corev1.ResourceEphemeralStorage: *resource.NewQuantity(int64(ephemeralLimitGi)<<30, resource.BinarySI),
			}},
		}}
	}
	return p
}

func newSyncer(t *testing.T, so *fakeSoT, stats StatsFetcher, objs ...runtime.Object) (*Syncer, client.Client) {
	t.Helper()
	c := fake.NewClientBuilder().WithScheme(scheme.Scheme).WithRuntimeObjects(objs...).Build()
	return &Syncer{Client: c, SoT: so, Namespace: "gshare-sessions", Stats: stats}, c
}

func TestTickReportsUsageForMountedClaimsOnly(t *testing.T) {
	so := &fakeSoT{}
	stats := func(_ context.Context, node string) ([]byte, error) {
		if node != "gpu-1" {
			t.Fatalf("unexpected node %q", node)
		}
		return []byte(`{"pods":[{"podRef":{"name":"ses-ses-1","namespace":"gshare-sessions"},
		  "ephemeral-storage":{"usedBytes":17179869184},"volume":[
		  {"usedBytes":3221225472,"pvcRef":{"name":"vol-a","namespace":"gshare-sessions"}},
		  {"usedBytes":99,"pvcRef":{"name":"other","namespace":"elsewhere"}}]}]}`), nil
	}
	s, _ := newSyncer(t, so, stats,
		pvc("vol-a", "vol_A", 10), pvc("vol-b", "vol_B", 5), sessionPod("ses-1", "gpu-1", "vol-a", 20))
	if err := s.Tick(context.Background()); err != nil {
		t.Fatal(err)
	}
	if len(so.got) != 2 {
		t.Fatalf("observed %d, want 2", len(so.got))
	}
	byName := map[string]sot.VolumeObserved{}
	for _, o := range so.got {
		byName[o.Name] = o
	}
	a, b := byName["vol-a"], byName["vol-b"]
	if a.VolumeID != "vol_A" || !a.Mounted || a.UsedBytes == nil || *a.UsedBytes != 3221225472 || a.CapacityGb != 10 {
		t.Errorf("vol-a observed wrong: %+v", a)
	}
	if b.Mounted || b.UsedBytes != nil || b.CapacityGb != 5 {
		t.Errorf("vol-b observed wrong: %+v", b)
	}
	if len(so.sessions) != 1 {
		t.Fatalf("sessions = %+v, want exactly one", so.sessions)
	}
	sd := so.sessions[0]
	if sd.Name != "ses-1" || sd.EphemeralUsedBytes != 17179869184 || sd.EphemeralLimitBytes != 20<<30 {
		t.Errorf("session disk observed wrong: %+v", sd)
	}
}

func TestTickReportsSessionDiskWithoutAnyClaims(t *testing.T) {
	so := &fakeSoT{}
	stats := func(_ context.Context, node string) ([]byte, error) {
		if node != "gpu-2" {
			t.Fatalf("unexpected node %q", node)
		}
		return []byte(`{"pods":[{"podRef":{"name":"ses-ses-abc123","namespace":"gshare-sessions"},
		  "ephemeral-storage":{"usedBytes":1073741824}}]}`), nil
	}
	s, _ := newSyncer(t, so, stats, sessionPod("ses-abc123", "gpu-2", "", 10))
	if err := s.Tick(context.Background()); err != nil {
		t.Fatal(err)
	}
	if len(so.got) != 0 {
		t.Errorf("observed %d claims, want none", len(so.got))
	}
	if len(so.sessions) != 1 {
		t.Fatalf("sessions = %+v, want exactly one", so.sessions)
	}
	sd := so.sessions[0]
	if sd.Name != "ses-abc123" || sd.EphemeralUsedBytes != 1073741824 || sd.EphemeralLimitBytes != 10<<30 {
		t.Errorf("session disk observed wrong: %+v", sd)
	}
}

func TestTickSkipsSessionPodsWithoutEphemeralLimit(t *testing.T) {
	so := &fakeSoT{}
	stats := func(_ context.Context, _ string) ([]byte, error) {
		return []byte(`{"pods":[{"podRef":{"name":"ses-ses-nolimit","namespace":"gshare-sessions"},
		  "ephemeral-storage":{"usedBytes":5}}]}`), nil
	}
	s, _ := newSyncer(t, so, stats,
		pvc("vol-a", "vol_A", 10), sessionPod("ses-nolimit", "gpu-1", "vol-a", 0))
	if err := s.Tick(context.Background()); err != nil {
		t.Fatal(err)
	}
	if len(so.sessions) != 0 {
		t.Errorf("sessions = %+v, want none (pod has no ephemeral-storage limit)", so.sessions)
	}
}

func TestTickSendsNoSessionsWhenStatsNil(t *testing.T) {
	so := &fakeSoT{}
	s, _ := newSyncer(t, so, nil, pvc("vol-a", "vol_A", 10), sessionPod("ses-1", "gpu-1", "vol-a", 20))
	if err := s.Tick(context.Background()); err != nil {
		t.Fatal(err)
	}
	if len(so.got) != 1 {
		t.Errorf("observed %d claims, want 1 (volume tick must keep working without stats)", len(so.got))
	}
	if len(so.sessions) != 0 {
		t.Errorf("sessions = %+v, want none when stats are unavailable", so.sessions)
	}
}

func TestEphemeralFromSummary(t *testing.T) {
	raw := []byte(`{"pods":[
	  {"podRef":{"name":"ses-ses-a","namespace":"gshare-sessions"},"ephemeral-storage":{"usedBytes":123}},
	  {"podRef":{"name":"ses-ses-b","namespace":"elsewhere"},"ephemeral-storage":{"usedBytes":456}},
	  {"podRef":{"name":"ses-ses-c","namespace":"gshare-sessions"}}]}`)
	got := ephemeralFromSummary(raw, "gshare-sessions")
	if len(got) != 1 || got["ses-ses-a"] != 123 {
		t.Errorf("ephemeralFromSummary = %v, want only ses-ses-a=123", got)
	}
	if len(ephemeralFromSummary([]byte("not json"), "gshare-sessions")) != 0 {
		t.Error("malformed summary must yield an empty map")
	}
}

func TestTickGrowsClaimToDirectedQuota(t *testing.T) {
	want := 20
	so := &fakeSoT{answer: sot.VolumeSyncResult{Volumes: []sot.VolumeDirective{{Name: "vol-a", QuotaGb: &want}}}}
	s, c := newSyncer(t, so, nil, pvc("vol-a", "vol_A", 10))
	if err := s.Tick(context.Background()); err != nil {
		t.Fatal(err)
	}
	var got corev1.PersistentVolumeClaim
	if err := c.Get(context.Background(), types.NamespacedName{Namespace: "gshare-sessions", Name: "vol-a"}, &got); err != nil {
		t.Fatal(err)
	}
	if requestGb(&got) != 20 {
		t.Errorf("request = %dGi, want 20Gi", requestGb(&got))
	}
}

func TestTickNeverShrinks(t *testing.T) {
	want := 5
	so := &fakeSoT{answer: sot.VolumeSyncResult{Volumes: []sot.VolumeDirective{{Name: "vol-a", QuotaGb: &want}}}}
	s, c := newSyncer(t, so, nil, pvc("vol-a", "vol_A", 10))
	if err := s.Tick(context.Background()); err != nil {
		t.Fatal(err)
	}
	var got corev1.PersistentVolumeClaim
	_ = c.Get(context.Background(), types.NamespacedName{Namespace: "gshare-sessions", Name: "vol-a"}, &got)
	if requestGb(&got) != 10 {
		t.Errorf("request = %dGi, want unchanged 10Gi", requestGb(&got))
	}
}

func TestTickReclaimsOnlyUnmountedClaims(t *testing.T) {
	so := &fakeSoT{answer: sot.VolumeSyncResult{Volumes: []sot.VolumeDirective{
		{Name: "vol-a", Reclaim: true}, {Name: "vol-b", Reclaim: true},
	}}}
	s, c := newSyncer(t, so, nil,
		pvc("vol-a", "vol_A", 10), pvc("vol-b", "vol_B", 10), podUsing("ses-1", "gpu-1", "vol-a"))
	if err := s.Tick(context.Background()); err != nil {
		t.Fatal(err)
	}
	var a, b corev1.PersistentVolumeClaim
	if err := c.Get(context.Background(), types.NamespacedName{Namespace: "gshare-sessions", Name: "vol-a"}, &a); err != nil {
		t.Errorf("mounted vol-a must survive: %v", err)
	}
	err := c.Get(context.Background(), types.NamespacedName{Namespace: "gshare-sessions", Name: "vol-b"}, &b)
	if !apierrors.IsNotFound(err) {
		t.Errorf("vol-b should be reclaimed, got err=%v", err)
	}
}

func TestTickIgnoresUnlabelledClaims(t *testing.T) {
	so := &fakeSoT{}
	foreign := &corev1.PersistentVolumeClaim{ObjectMeta: metav1.ObjectMeta{Namespace: "gshare-sessions", Name: "not-ours"}}
	s, _ := newSyncer(t, so, nil, foreign)
	if err := s.Tick(context.Background()); err != nil {
		t.Fatal(err)
	}
	if len(so.got) != 0 {
		t.Errorf("reported %d claims, want none", len(so.got))
	}
}

// An idle cluster is exactly when an administrator asks how much room the pool has left. The tick
// used to return early the moment there were no session volumes and no scratch-disk readings,
// which skipped the capacity report with everything else.
func TestTickReportsPoolCapacityWithNothingElseToSay(t *testing.T) {
	scheme := runtime.NewScheme()
	if err := corev1.AddToScheme(scheme); err != nil {
		t.Fatal(err)
	}
	if err := storagev1.AddToScheme(scheme); err != nil {
		t.Fatal(err)
	}
	cap := resource.MustParse("1424Gi")
	reader := fake.NewClientBuilder().WithScheme(scheme).WithObjects(
		&storagev1.CSIStorageCapacity{
			ObjectMeta:       metav1.ObjectMeta{Name: "csisc-1", Namespace: "gshare-storage"},
			StorageClassName: "gshare-data",
			Capacity:         &cap,
		},
		&storagev1.CSIStorageCapacity{ // another class: must not be picked up
			ObjectMeta:       metav1.ObjectMeta{Name: "csisc-2", Namespace: "gshare-storage"},
			StorageClassName: "other",
			Capacity:         &cap,
		},
	).Build()
	f := &fakeSoT{}
	s := &Syncer{
		Client:       fake.NewClientBuilder().WithScheme(scheme).Build(),
		SoT:          f,
		Namespace:    "gshare-sessions",
		StorageClass: "gshare-data",
		Reader:       reader,
	}
	if err := s.Tick(context.Background()); err != nil {
		t.Fatalf("tick: %v", err)
	}
	if len(f.pools) != 1 || f.pools[0].StorageClass != "gshare-data" {
		t.Fatalf("expected one gshare-data capacity, got %+v", f.pools)
	}
	if f.pools[0].CapacityBytes != cap.Value() {
		t.Fatalf("capacity = %d, want %d", f.pools[0].CapacityBytes, cap.Value())
	}
}

// No StorageClass configured, or no reader, means nothing to match against — and then an idle
// cluster still skips the call entirely rather than posting an empty report every few minutes.
func TestTickStaysQuietWithoutAStorageClass(t *testing.T) {
	scheme := runtime.NewScheme()
	if err := corev1.AddToScheme(scheme); err != nil {
		t.Fatal(err)
	}
	f := &fakeSoT{}
	s := &Syncer{
		Client:    fake.NewClientBuilder().WithScheme(scheme).Build(),
		SoT:       f,
		Namespace: "gshare-sessions",
	}
	if err := s.Tick(context.Background()); err != nil {
		t.Fatalf("tick: %v", err)
	}
	if f.called {
		t.Fatal("expected no report")
	}
}
