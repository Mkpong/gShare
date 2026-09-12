/*
Pod Security Admission checks on the builder's output: every non-privileged session pod, in
every mode, must satisfy the `restricted` profile; a policy-granted privileged session must stay
within `baseline`.
*/
package podbuilder

import (
	"testing"

	corev1 "k8s.io/api/core/v1"

	gsharev1 "github.com/gshare/operator/api/v1"
)

// baselineCaps is the capability set PSA baseline still admits being added.
var baselineCaps = map[corev1.Capability]bool{
	"AUDIT_WRITE": true, "CHOWN": true, "DAC_OVERRIDE": true, "FOWNER": true, "FSETID": true,
	"KILL": true, "MKNOD": true, "NET_BIND_SERVICE": true, "SETFCAP": true, "SETGID": true,
	"SETPCAP": true, "SETUID": true, "SYS_CHROOT": true,
}

func modes() map[string]struct {
	b *Builder
	s *gsharev1.GShareSession
} {
	mk := func(spec gsharev1.GShareSessionSpec) *gsharev1.GShareSession {
		s := &gsharev1.GShareSession{Spec: spec}
		s.Name = "ses-x"
		s.Spec.Image = "img"
		return s
	}
	return map[string]struct {
		b *Builder
		s *gsharev1.GShareSession
	}{
		"fractional": {&Builder{}, mk(gsharev1.GShareSessionSpec{ResourceClass: "gpu", Mode: "fractional", GpuMemMb: 4000, GpuCores: 30})},
		"exclusive":  {&Builder{}, mk(gsharev1.GShareSessionSpec{ResourceClass: "gpu", Mode: "exclusive"})},
		"exclusive-fullcard": {&Builder{PerCardMode: true}, mk(gsharev1.GShareSessionSpec{ResourceClass: "gpu", Mode: "exclusive",
			PinnedGpuUuid: "GPU-1"})},
		"mig":             {&Builder{}, mk(gsharev1.GShareSessionSpec{ResourceClass: "gpu", Mode: "mig", MigProfile: "1g.5gb"})},
		"cpu":             {&Builder{}, mk(gsharev1.GShareSessionSpec{ResourceClass: "cpu"})},
		"borrow-bypass":   {&Builder{}, mk(gsharev1.GShareSessionSpec{ResourceClass: "gpu", Mode: "exclusive", BorrowedGpuUuid: "GPU-1", BorrowedNode: "n1"})},
		"borrow-extender": {&Builder{HAMiYieldExtender: true}, mk(gsharev1.GShareSessionSpec{ResourceClass: "gpu", Mode: "exclusive", BorrowedGpuUuid: "GPU-1"})},
		"with-volume": {&Builder{}, mk(gsharev1.GShareSessionSpec{ResourceClass: "gpu", Mode: "fractional", GpuMemMb: 1, GpuCores: 1,
			Volumes: []gsharev1.VolumeSpec{{Name: "vol_A", MountPath: "/data", Mode: "ReadWriteOnce"}}})},
	}
}

// assertBaseline covers what both profiles forbid: host namespaces, privileged mode, host ports,
// host paths, and any capability outside the baseline set.
func assertBaseline(t *testing.T, name string, pod *corev1.Pod) {
	t.Helper()
	if pod.Spec.HostNetwork || pod.Spec.HostPID || pod.Spec.HostIPC {
		t.Fatalf("%s: host namespaces are forbidden", name)
	}
	for _, v := range pod.Spec.Volumes {
		if v.HostPath != nil {
			t.Fatalf("%s: hostPath volume %q is forbidden", name, v.Name)
		}
		if v.PersistentVolumeClaim == nil && v.ConfigMap == nil && v.EmptyDir == nil && v.Secret == nil && v.Projected == nil {
			t.Fatalf("%s: volume %q uses a type outside the restricted allow-list", name, v.Name)
		}
	}
	all := append(append([]corev1.Container{}, pod.Spec.InitContainers...), pod.Spec.Containers...)
	for _, c := range all {
		sc := c.SecurityContext
		if sc == nil {
			t.Fatalf("%s/%s: container securityContext missing", name, c.Name)
		}
		if sc.Privileged != nil && *sc.Privileged {
			t.Fatalf("%s/%s: privileged containers are forbidden", name, c.Name)
		}
		if sc.Capabilities != nil {
			for _, add := range sc.Capabilities.Add {
				if !baselineCaps[add] {
					t.Fatalf("%s/%s: capability %s is outside PSA baseline", name, c.Name, add)
				}
			}
		}
		for _, p := range c.Ports {
			if p.HostPort != 0 {
				t.Fatalf("%s/%s: hostPort is forbidden", name, c.Name)
			}
		}
	}
	if pod.Spec.SecurityContext == nil || pod.Spec.SecurityContext.SeccompProfile == nil ||
		pod.Spec.SecurityContext.SeccompProfile.Type != corev1.SeccompProfileTypeRuntimeDefault {
		t.Fatalf("%s: pod seccompProfile must be RuntimeDefault", name)
	}
}

// assertRestricted adds the restricted-only rules: runAsNonRoot, no privilege escalation,
// drop ALL with no additions.
func assertRestricted(t *testing.T, name string, pod *corev1.Pod) {
	t.Helper()
	assertBaseline(t, name, pod)
	psc := pod.Spec.SecurityContext
	if psc.RunAsNonRoot == nil || !*psc.RunAsNonRoot {
		t.Fatalf("%s: pod runAsNonRoot must be true", name)
	}
	if psc.RunAsUser != nil && *psc.RunAsUser == 0 {
		t.Fatalf("%s: runAsUser 0 contradicts runAsNonRoot", name)
	}
	all := append(append([]corev1.Container{}, pod.Spec.InitContainers...), pod.Spec.Containers...)
	for _, c := range all {
		sc := c.SecurityContext
		if sc.AllowPrivilegeEscalation == nil || *sc.AllowPrivilegeEscalation {
			t.Fatalf("%s/%s: allowPrivilegeEscalation must be false", name, c.Name)
		}
		if sc.Capabilities == nil || len(sc.Capabilities.Drop) != 1 || sc.Capabilities.Drop[0] != "ALL" {
			t.Fatalf("%s/%s: capabilities must drop ALL, got %v", name, c.Name, sc.Capabilities)
		}
		if len(sc.Capabilities.Add) != 0 {
			t.Fatalf("%s/%s: restricted allows no added capabilities, got %v", name, c.Name, sc.Capabilities.Add)
		}
	}
	if pod.Spec.AutomountServiceAccountToken == nil || *pod.Spec.AutomountServiceAccountToken {
		t.Fatalf("%s: the session must not mount a service-account token", name)
	}
}

func TestEveryModeSatisfiesPSARestricted(t *testing.T) {
	for name, tc := range modes() {
		pod := tc.b.BuildPod(tc.s)
		assertRestricted(t, name, pod)
		if len(pod.Spec.Containers) != 1 || pod.Spec.Containers[0].Name != "session" {
			t.Fatalf("%s: expected exactly one container named session", name)
		}
		// CPU/RAM/disk are Guaranteed: request == limit for every mode.
		res := pod.Spec.Containers[0].Resources
		for _, k := range []corev1.ResourceName{corev1.ResourceCPU, corev1.ResourceMemory, corev1.ResourceEphemeralStorage} {
			if res.Requests[k] != res.Limits[k] {
				t.Fatalf("%s: %s request %v != limit %v", name, k, res.Requests[k], res.Limits[k])
			}
		}
	}
}

func TestPrivilegedSessionStaysWithinPSABaseline(t *testing.T) {
	s := &gsharev1.GShareSession{Spec: gsharev1.GShareSessionSpec{ResourceClass: "gpu", Mode: "fractional",
		GpuMemMb: 1, GpuCores: 1, Image: "img", Privileged: true}}
	s.Name = "ses-root"
	pod := (&Builder{}).BuildPod(s)
	assertBaseline(t, "privileged", pod)
	psc := pod.Spec.SecurityContext
	if psc.RunAsNonRoot == nil || *psc.RunAsNonRoot || psc.RunAsUser == nil || *psc.RunAsUser != 0 {
		t.Fatalf("privileged session runs as root by design, got %+v", psc)
	}
	sc := pod.Spec.Containers[0].SecurityContext
	if sc.Capabilities == nil || len(sc.Capabilities.Drop) != 1 || sc.Capabilities.Drop[0] != "ALL" {
		t.Fatalf("privileged session must still start from drop ALL, got %v", sc.Capabilities)
	}
	if sc.Privileged != nil && *sc.Privileged {
		t.Fatalf("privileged session must never set securityContext.privileged")
	}
}

func TestNonPrivilegedRunsAsTheCoderUID(t *testing.T) {
	s := &gsharev1.GShareSession{Spec: gsharev1.GShareSessionSpec{ResourceClass: "cpu", Image: "img"}}
	pod := (&Builder{}).BuildPod(s)
	if got := *pod.Spec.SecurityContext.RunAsUser; got != 1000 {
		t.Fatalf("expected uid 1000, got %d", got)
	}
	if got := *pod.Spec.SecurityContext.FSGroup; got != 1000 {
		t.Fatalf("expected fsGroup 1000, got %d", got)
	}
}
