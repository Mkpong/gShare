/*
The session pod must carry the labels the shipped NetworkPolicies select on, and the Service must
keep selecting the pod without them — see podLabels().
*/
package podbuilder

import (
	"testing"

	gsharev1 "github.com/gshare/operator/api/v1"
)

func TestPodCarriesTheNetworkPolicySelectorLabels(t *testing.T) {
	for _, tc := range []struct {
		name          string
		resourceClass string
	}{
		{"gpu session", "gpu"},
		{"cpu session", "cpu"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			s := &gsharev1.GShareSession{Spec: gsharev1.GShareSessionSpec{
				ResourceClass: tc.resourceClass, Mode: "fractional", Image: "img",
			}}
			s.Name = "ses-x"
			got := (&Builder{}).BuildPod(s).Labels

			if got["gshare.io/workload"] != "session" {
				t.Fatalf("session-egress-allow selects gshare.io/workload=session, pod has %q",
					got["gshare.io/workload"])
			}
			if got["gshare.io/resource-class"] != tc.resourceClass {
				t.Fatalf("cpu-data-egress-allow selects gshare.io/resource-class, pod has %q",
					got["gshare.io/resource-class"])
			}
			if got["gshare.io/session"] != "ses-x" {
				t.Fatalf("the per-session label must survive, got %q", got["gshare.io/session"])
			}
		})
	}
}

func TestServiceSelectorStaysMatchableByOlderPods(t *testing.T) {
	// The Service selector must not demand the new labels: a pod created by a previous operator
	// version carries only gshare.io/session, and the Service has to keep routing to it.
	s := &gsharev1.GShareSession{Spec: gsharev1.GShareSessionSpec{
		ResourceClass: "gpu", Mode: "exclusive", Image: "img",
	}}
	s.Name = "ses-y"
	sel := (&Builder{}).BuildService(s).Spec.Selector

	if len(sel) != 1 || sel["gshare.io/session"] != "ses-y" {
		t.Fatalf("service selector must stay {gshare.io/session}, got %v", sel)
	}
}
