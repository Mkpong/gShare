/*
SessionReconciler reconciles GShareSession (desired) -> actual K8s objects
(Pod/Service/Ingress/Secret) and writes back .status + a SoT callback.

  - Control plane applies the CR; the operator owns child lifecycle via owner refs + a finalizer.
  - Phase transitions are reported to the SoT control plane (running->consume, terminated->settle).
    Credits live only in the control plane.
  - trace_id is restored from CR annotation gshare.io/traceparent and carried on the callback.
*/
package controller

import (
	"context"
	"sort"
	"strconv"
	"strings"
	"time"

	corev1 "k8s.io/api/core/v1"
	netv1 "k8s.io/api/networking/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/util/retry"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
	"sigs.k8s.io/controller-runtime/pkg/log"

	gsharev1 "github.com/gshare/operator/api/v1"
	"github.com/gshare/operator/internal/podbuilder"
	"github.com/gshare/operator/internal/sot"
)

const (
	// finalizer ties child cleanup + terminated reporting to CR deletion.
	finalizer = "gshare.io/session-finalizer"
	// traceparentAnnotation carries the W3C traceparent injected by the SoT control plane.
	traceparentAnnotation = "gshare.io/traceparent"
	// pauseReasonAnnotation is stamped by the idle reaper; forwarded as the Paused message.
	pauseReasonAnnotation = "gshare.io/pause-reason"
	// yieldedGPUsAnnotation lists (CSV) the GPU UUIDs a node has in-place-yielded — the feed the
	// HAMi scheduler-extender reads to treat a card as preemptible capacity. (build/hami-fork)
	yieldedGPUsAnnotation = "gshare.io/yielded-gpus"
)

// SessionReconciler reconciles a GShareSession object.
type SessionReconciler struct {
	client.Client
	// EventReader reads Events uncached (mgr.GetAPIReader()); used only on terminal pod
	// transitions to recover an eviction cause. Nil in tests that do not need it.
	EventReader client.Reader
	Scheme      *runtime.Scheme
	Builder     *podbuilder.Builder
	SoT         sot.Reporter
	ClusterID   string
	// Checkpointer drives lossless-pause checkpoint/yield/resume via a node agent. Nil when no
	// agent is wired — the pause path then falls back to cold pause.
	Checkpointer Checkpointer
	// VolumeStorageClass names the StorageClass backing session-volume PVCs; empty uses the
	// cluster default.
	VolumeStorageClass string
}

// Checkpointer drives a privileged node agent (gshare-infra). See docs/paper/lossless-pause.md.
type Checkpointer interface {
	// Checkpoint dumps GPU/process state; returns a storage ref recorded on status.checkpointRef.
	Checkpoint(ctx context.Context, s *gsharev1.GShareSession, pod *corev1.Pod) (ref string, err error)
	// Cleanup reclaims a node-local checkpoint (content-store image + dir). Fire-and-forget; safe
	// when no checkpoint exists. Used on cold-resume / terminate.
	Cleanup(ctx context.Context, sessionName, nodeName string) error
	// Yield evicts VRAM in-place (Pod stays alive) so the physical card is freed/lendable.
	Yield(ctx context.Context, s *gsharev1.GShareSession, pod *corev1.Pod) error
	// Resume toggles a yielded session's VRAM back into its live process (lossless, no Pod recreate).
	Resume(ctx context.Context, s *gsharev1.GShareSession, nodeName string) error
}

// +kubebuilder:rbac:groups=gshare.io,resources=gsharesessions,verbs=get;list;watch;update;patch
// +kubebuilder:rbac:groups=gshare.io,resources=gsharesessions/status,verbs=get;update;patch
// +kubebuilder:rbac:groups=gshare.io,resources=gsharesessions/finalizers,verbs=update
// +kubebuilder:rbac:groups="",resources=pods;services;secrets,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=networking.k8s.io,resources=ingresses,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=batch,resources=jobs,verbs=get;list;watch;create;delete

// Reconcile drives desired -> actual for one GShareSession.
func (r *SessionReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	logger := log.FromContext(ctx)

	var s gsharev1.GShareSession
	if err := r.Get(ctx, req.NamespacedName, &s); err != nil {
		return ctrl.Result{}, client.IgnoreNotFound(err)
	}

	traceID := traceIDFromAnnotations(s.Annotations)

	// Deletion path: finalizer cleans children, then reports Terminated (-> settle in the control plane).
	if !s.DeletionTimestamp.IsZero() {
		if controllerutil.ContainsFinalizer(&s, finalizer) {
			if err := r.cleanupChildren(ctx, &s); err != nil {
				return ctrl.Result{}, err
			}
			// GC any lingering lossless checkpoint (node-local image + dir). Best-effort.
			if s.Status.CheckpointRef != "" && r.Checkpointer != nil {
				if cerr := r.Checkpointer.Cleanup(ctx, s.Name, s.Status.CheckpointNode); cerr != nil {
					logger.Error(cerr, "checkpoint cleanup on terminate failed (will leak)", "session", s.Name, "node", s.Status.CheckpointNode)
				}
			}
			_ = r.SoT.Report(ctx, s.Name, sot.StatusEvent{Generation: s.Generation, Phase: "Terminated", TraceID: traceID})
			controllerutil.RemoveFinalizer(&s, finalizer)
			if err := r.Update(ctx, &s); err != nil {
				return ctrl.Result{}, err
			}
		}
		return ctrl.Result{}, nil
	}

	if controllerutil.AddFinalizer(&s, finalizer) {
		if err := r.Update(ctx, &s); err != nil {
			return ctrl.Result{}, err
		}
	}

	// Pause path: spec.paused deletes the Pod (freeing the GPU) but keeps the CR and its
	// Secret/Service/Ingress. Phase=Paused (not Terminated) so the control plane does not
	// settle. Resuming (paused=false) falls through to the normal flow and recreates the Pod.
	if s.Spec.Paused {
		// Idempotent: already Paused means the Pod is released and status (incl. CheckpointRef)
		// is recorded; a re-reconcile must NOT re-checkpoint (GPU is unbound, so a second attempt
		// fails with "no bound GPU uuid" and would clobber CheckpointRef).
		if s.Status.Phase == "Paused" {
			// Yield demotion: a yielded session (yieldState=Yielded) whose pauseMode is no longer
			// "yield" (backend cold-demoted on reservation-TTL expiry) releases the host-RAM hold and
			// goes cold; subsequent resume is cold. Done atomically here (single reconcile) — the
			// backend only sets the desired spec, so there is no resume/pause CR-patch race.
			// (docs/paper/manuscript, §Design)
			if s.Status.YieldState == "Yielded" && s.Spec.PauseMode != "yield" {
				var live corev1.Pod
				podErr := r.Get(ctx, podKey(&s), &live)
				if podErr == nil && live.DeletionTimestamp.IsZero() {
					// Graceful demotion (not-lent only — backend sets gracefulDemote when the card is
					// physically free): toggle VRAM back into the live process, then delete the Pod with
					// its grace period so the job's SIGTERM handler saves a FRESH checkpoint before exit.
					// Resume failure (e.g. VRAM gate) degrades to plain cold delete (last periodic ckpt).
					if s.Spec.GracefulDemote && r.Checkpointer != nil {
						if rerr := r.Checkpointer.Resume(ctx, &s, live.Spec.NodeName); rerr != nil {
							logger.Error(rerr, "graceful-demote resume failed; cold-deleting without fresh checkpoint", "session", s.Name)
						} else {
							logger.Info("graceful-demote: VRAM restored; deleting Pod for fresh checkpoint-on-SIGTERM", "session", s.Name)
						}
					}
					if derr := r.Delete(ctx, &live); derr != nil && !apierrors.IsNotFound(derr) {
						return ctrl.Result{}, derr
					}
				} else if podErr != nil && !apierrors.IsNotFound(podErr) {
					return ctrl.Result{}, podErr
				}
				demoteNode, demoteUUID := live.Spec.NodeName, s.Status.BoundGpuUuid
				s.Status.YieldState = ""
				s.Status.EvictedVramMb = 0
				s.Status.LentTo = ""
				if uerr := r.Status().Update(ctx, &s); uerr != nil {
					return ctrl.Result{}, uerr
				}
				// Demoted — withdraw the card from the node's preemptible (yielded) pool.
				if aerr := r.setNodeYielded(ctx, demoteNode, demoteUUID, false); aerr != nil {
					logger.Error(aerr, "clear yielded-gpus node annotation failed", "session", s.Name)
				}
				logger.Info("yield reservation demoted to cold (host-RAM hold released)", "session", s.Name, "graceful", s.Spec.GracefulDemote)
			}
			return ctrl.Result{}, nil
		}
		var live corev1.Pod
		err := r.Get(ctx, podKey(&s), &live)

		// YIELD mode: keep the Pod alive, evict VRAM in place (physical card freed, lossless resume).
		// No checkpoint/delete; device-plugin allocation stays with the live Pod. Falls back to cold
		// pause if yield fails. (docs/paper/manuscript, §Design)
		if err == nil && s.Spec.PauseMode == "yield" && r.Checkpointer != nil {
			if yerr := r.Checkpointer.Yield(ctx, &s, &live); yerr != nil {
				logger.Error(yerr, "in-place yield failed; falling back to cold pause", "session", s.Name)
			} else {
				s.Status.Phase = "Paused"
				s.Status.YieldState = "Yielded"
				s.Status.EvictedVramMb = s.Spec.GpuMemMb // informational (exclusive: full card)
				s.Status.TraceID = traceID
				s.Status.ObservedGeneration = s.Generation
				if uerr := r.Status().Update(ctx, &s); uerr != nil {
					return ctrl.Result{}, uerr
				}
				// Advertise the freed card as preemptible capacity to the HAMi extender.
				if aerr := r.setNodeYielded(ctx, live.Spec.NodeName, s.Status.BoundGpuUuid, true); aerr != nil {
					logger.Error(aerr, "publish yielded-gpus node annotation failed", "session", s.Name)
				}
				_ = r.SoT.Report(ctx, s.Name, sot.StatusEvent{Generation: s.Generation, Phase: "Paused", YieldState: "Yielded", TraceID: traceID, Message: s.Annotations[pauseReasonAnnotation]})
				logger.Info("session yielded in-place (Pod alive, VRAM evicted)", "session", s.Name)
				return ctrl.Result{}, nil
			}
		}
		// Lossless pause: checkpoint the live Pod (cuda-checkpoint + CRIU) BEFORE deleting it.
		// Best-effort — any failure (or no checkpointer) degrades to cold pause (plain delete;
		// volumes preserved, no data loss).
		checkpointRef, checkpointNode := "", ""
		if err == nil && s.Spec.LosslessPause && r.Checkpointer != nil {
			if ref, cerr := r.Checkpointer.Checkpoint(ctx, &s, &live); cerr != nil {
				logger.Error(cerr, "lossless checkpoint failed; falling back to cold pause", "session", s.Name)
			} else {
				checkpointRef, checkpointNode = ref, live.Spec.NodeName // node holds the node-local checkpoint
				logger.Info("lossless checkpoint stored", "session", s.Name, "checkpointRef", ref, "node", checkpointNode)
			}
		}
		if err == nil {
			if live.DeletionTimestamp.IsZero() {
				if derr := r.Delete(ctx, &live); derr != nil && !apierrors.IsNotFound(derr) {
					return ctrl.Result{}, derr
				}
			}
		} else if !apierrors.IsNotFound(err) {
			return ctrl.Result{}, err
		}
		if s.Status.Phase != "Paused" || s.Status.CheckpointRef != checkpointRef {
			s.Status.Phase = "Paused"
			s.Status.BoundGpuUuid = ""
			s.Status.CheckpointRef = checkpointRef
			s.Status.CheckpointNode = checkpointNode
			s.Status.TraceID = traceID
			s.Status.ObservedGeneration = s.Generation
			if err := r.Status().Update(ctx, &s); err != nil {
				return ctrl.Result{}, err
			}
			_ = r.SoT.Report(ctx, s.Name, sot.StatusEvent{Generation: s.Generation, Phase: "Paused", TraceID: traceID, Message: s.Annotations[pauseReasonAnnotation]})
			logger.Info("session paused (pod released)", "session", s.Name, "lossless", checkpointRef != "")
		}
		return ctrl.Result{}, nil
	}

	// Resume from in-place yield: the Pod stayed alive; toggle VRAM back into the live process
	// (lossless, no Pod recreate). Idempotent — the agent no-ops if no yield state remains.
	// (docs/paper/manuscript, §Design)
	if s.Status.YieldState == "Yielded" && r.Checkpointer != nil {
		var live corev1.Pod
		if err := r.Get(ctx, podKey(&s), &live); err != nil {
			if apierrors.IsNotFound(err) {
				// Pod gone while yielded (node lost) — yield state is stale; clear and rebuild cold.
				s.Status.YieldState = ""
				if uerr := r.Status().Update(ctx, &s); uerr != nil {
					return ctrl.Result{}, uerr
				}
				return ctrl.Result{}, nil
			}
			return ctrl.Result{}, err
		}
		if rerr := r.Checkpointer.Resume(ctx, &s, live.Spec.NodeName); rerr != nil {
			logger.Error(rerr, "in-place resume(toggle) failed", "session", s.Name)
			return ctrl.Result{}, rerr
		}
		resumedUUID, resumedNode := s.Status.BoundGpuUuid, live.Spec.NodeName
		s.Status.YieldState = ""
		s.Status.EvictedVramMb = 0
		s.Status.LentTo = ""
		if uerr := r.Status().Update(ctx, &s); uerr != nil {
			return ctrl.Result{}, uerr
		}
		// Card reclaimed — withdraw it from the node's preemptible (yielded) pool.
		if aerr := r.setNodeYielded(ctx, resumedNode, resumedUUID, false); aerr != nil {
			logger.Error(aerr, "clear yielded-gpus node annotation failed", "session", s.Name)
		}
		logger.Info("session resumed in-place (VRAM restored into live Pod, lossless)", "session", s.Name)
		return ctrl.Result{}, nil // next reconcile observes Pod Running and reports normally
	}

	// 1) per-session Secret (ses-<id>-secret) from spec.connect.
	sec := r.Builder.BuildSecret(&s)
	if err := controllerutil.SetControllerReference(&s, sec, r.Scheme); err != nil {
		return ctrl.Result{}, err
	}
	if err := r.applyIfAbsent(ctx, sec); err != nil {
		return ctrl.Result{}, err
	}

	// Borrow lend-guard (defense-in-depth): before placing a borrow Pod on a yielded card, verify
	// the lend invariant at the cluster (the backend ledger already enforces it atomically). Refuse +
	// requeue if no yielded resident holds the card, or another spot session already has it.
	if s.Spec.BorrowedGpuUuid != "" {
		if ok, reason := r.borrowGuard(ctx, &s); !ok {
			logger.Info("borrow denied by lend guard; not placing Pod", "session", s.Name, "reason", reason)
			return ctrl.Result{Requeue: true}, nil
		}
	}

	// 1.5) PVCs backing spec.volumes — created here, once, and NOT owned by the session: a
	// volume outlives the sessions that mount it (that is the whole point of a volume).
	if err := r.ensureVolumeClaims(ctx, &s); err != nil {
		return ctrl.Result{}, err
	}

	// 1.7) A live Pod sitting on a node the spec now excludes (a drain vacated the session and
	// the resume arrived before the pause had torn the Pod down) is replaced: delete it here and
	// let the next reconcile build the Pod elsewhere. Without this the "rescheduled" session
	// quietly stays put on the node being drained.
	{
		var cur corev1.Pod
		if err := r.Get(ctx, podKey(&s), &cur); err == nil && cur.DeletionTimestamp.IsZero() {
			replace := ""
			if cur.Spec.NodeName == "" && cur.Spec.Affinity != nil && cur.Spec.Affinity.NodeAffinity != nil {
				// A Pending pod from an earlier operator that baked node exclusion into affinity:
				// it would never schedule once the cordon lifted. Rebuild it without.
				replace = "legacy node affinity"
			} else if cur.Spec.NodeName != "" && r.nodeExcluded(ctx, cur.Spec.NodeName, s.Spec.ExcludedNodes) {
				replace = "node " + cur.Spec.NodeName + " is cordoned/unready"
			}
			if replace != "" {
				logger.Info("replacing pod", "session", s.Name, "why", replace)
				if derr := r.Delete(ctx, &cur); derr != nil && !apierrors.IsNotFound(derr) {
					return ctrl.Result{}, derr
				}
				return ctrl.Result{RequeueAfter: 3 * time.Second}, nil
			}
		}
	}

	// 2) desired Pod by mode.
	pod := r.Builder.BuildPod(&s)
	if err := controllerutil.SetControllerReference(&s, pod, r.Scheme); err != nil {
		return ctrl.Result{}, err
	}
	if err := r.applyIfAbsent(ctx, pod); err != nil {
		if apierrors.IsInvalid(err) {
			// A structurally invalid pod will never succeed by retrying — tell the control plane
			// (session -> error with the reason) instead of crash-looping into a silent pending.
			_ = r.SoT.Report(ctx, s.Name, sot.StatusEvent{Generation: s.Generation,
				Phase: "Error", Message: "pod rejected: " + err.Error(),
			})
			logger.Error(err, "pod spec rejected by the API server; reported error", "session", s.Name)
			return ctrl.Result{}, nil
		}
		return ctrl.Result{}, err
	}

	// 3) connection Service/Ingress for GPU/image sessions.
	if s.Spec.ResourceClass == "gpu" || s.Spec.Image != "" {
		svc := r.Builder.BuildService(&s)
		_ = controllerutil.SetControllerReference(&s, svc, r.Scheme)
		if err := r.applyIfAbsent(ctx, svc); err != nil {
			return ctrl.Result{}, err
		}
		// Two Ingress objects per session: the apps Ingress (no rewrite) and the vscode
		// Ingress (prefix-stripping rewrite). Split because the rewrite annotation is per-Ingress.
		ing := r.Builder.BuildIngress(&s)
		_ = controllerutil.SetControllerReference(&s, ing, r.Scheme)
		if err := r.applyIfAbsent(ctx, ing); err != nil {
			return ctrl.Result{}, err
		}
		vsIng := r.Builder.BuildVSCodeIngress(&s)
		_ = controllerutil.SetControllerReference(&s, vsIng, r.Scheme)
		if err := r.applyIfAbsent(ctx, vsIng); err != nil {
			return ctrl.Result{}, err
		}
	}

	// 4) observe Pod -> update status -> report to SoT on phase change.
	var live corev1.Pod
	if err := r.Get(ctx, podKey(&s), &live); err != nil && !apierrors.IsNotFound(err) {
		return ctrl.Result{}, err
	}
	phase, gpu := mapPhase(&live), boundGPU(&live)
	if live.UID != "" && !live.DeletionTimestamp.IsZero() {
		// The Pod is being torn down while the session is still desired: a manual delete, a
		// node eviction, or a pause the resume overtook. Its exit is not the session's end — the
		// next reconcile rebuilds it — so it must not surface as Terminated/Error, which would
		// settle the bill and release the reservation out from under a session that continues.
		phase = "Preparing"
	}
	restarts, cstate := containerFacts(&live)
	if phase == s.Status.Phase && live.UID != "" && (phase == "Running" || phase == "Preparing") {
		// Nothing changed: still a heartbeat. The control plane never inspects Kubernetes, so
		// this is how it learns the pod is still there (and how a crash loop surfaces — a pod
		// whose container keeps restarting stays Running from the phase's point of view).
		_ = r.SoT.Report(ctx, s.Name, sot.StatusEvent{Generation: s.Generation,
			Phase: "Heartbeat", BoundGpuUUID: gpu, NodeName: live.Spec.NodeName,
			PodRef: live.Namespace + "/" + live.Name, RestartCount: restarts, ContainerState: cstate,
			TraceID: traceID,
		})
		return ctrl.Result{RequeueAfter: heartbeatInterval}, nil
	}
	if phase != s.Status.Phase {
		s.Status.Phase = phase
		s.Status.BoundGpuUuid = gpu
		// Resume recreates the Pod cold (restore is unsupported; see lossless-pause.md), so the prior
		// checkpoint is stale. GC its node-local artifacts before clearing the ref. Best-effort.
		if s.Status.CheckpointRef != "" && r.Checkpointer != nil {
			if cerr := r.Checkpointer.Cleanup(ctx, s.Name, s.Status.CheckpointNode); cerr != nil {
				logger.Error(cerr, "stale checkpoint cleanup failed (will leak)", "session", s.Name, "node", s.Status.CheckpointNode)
			}
		}
		s.Status.CheckpointRef = ""
		s.Status.CheckpointNode = ""
		s.Status.PodRef = live.Namespace + "/" + live.Name
		s.Status.TraceID = traceID
		s.Status.ObservedGeneration = s.Generation
		if err := r.Status().Update(ctx, &s); err != nil {
			return ctrl.Result{}, err
		}
		// running->consume / error->refund decision (made only in the control plane).
		ev := sot.StatusEvent{Generation: s.Generation,
			Phase:          phase,
			BoundGpuUUID:   gpu,
			NodeName:       live.Spec.NodeName,
			PodRef:         s.Status.PodRef,
			UsedMemMB:      s.Status.UsedMemMb,
			RestartCount:   restarts,
			ContainerState: cstate,
			TraceID:        traceID,
		}
		if live.Status.Phase == corev1.PodFailed || live.Status.Phase == corev1.PodSucceeded {
			// Carry the kubelet's failure cause (e.g. "Evicted: Pod ephemeral local storage usage
			// exceeds the total limit of containers 20Gi.") so the control plane can tell the
			// user why the session ended, not just that it did.
			ev.Message = failureMessage(live.Status.Reason, live.Status.Message)
			if ev.Message == "" {
				// A gracefully-evicted pod (entrypoint exits 0 on SIGTERM) ends SUCCEEDED with an
				// empty reason; the only durable evidence is the kubelet's Evicted Event. One
				// uncached read on a terminal transition only.
				ev.Message = evictionMessage(ctx, r.EventReader, &live)
			}
		}
		_ = r.SoT.Report(ctx, s.Name, ev)
		logger.Info("session phase changed", "session", s.Name, "phase", phase)
	}
	if live.UID != "" && (phase == "Running" || phase == "Preparing") {
		return ctrl.Result{RequeueAfter: heartbeatInterval}, nil
	}
	return ctrl.Result{}, nil
}

// heartbeatInterval is how often a live session is re-reported to the control plane. The
// control plane's SESSION_STALE_SEC must comfortably exceed it.
const heartbeatInterval = 60 * time.Second

// containerFacts reads the session container's restart count and a compact state string
// ("Running", "Waiting:CrashLoopBackOff", "Terminated:OOMKilled") off the pod status.
func containerFacts(p *corev1.Pod) (int, string) {
	if p == nil || len(p.Status.ContainerStatuses) == 0 {
		return 0, ""
	}
	cs := p.Status.ContainerStatuses[0]
	for _, c := range p.Status.ContainerStatuses {
		if c.Name == "session" {
			cs = c
			break
		}
	}
	state := "Running"
	switch {
	case cs.State.Waiting != nil:
		state = "Waiting:" + cs.State.Waiting.Reason
	case cs.State.Terminated != nil:
		state = "Terminated:" + cs.State.Terminated.Reason
	}
	return int(cs.RestartCount), state
}

// borrowGuard verifies the in-place-yield lend invariant before a borrow Pod is placed: the target
// card must be held by a yielded/lent resident session, and at most one spot session per card. Cluster-side
// defense-in-depth (the backend ledger enforces it atomically). Returns (false, reason) to
// deny+requeue. (docs/paper/manuscript, §Design)
func (r *SessionReconciler) borrowGuard(ctx context.Context, s *gsharev1.GShareSession) (bool, string) {
	var list gsharev1.GShareSessionList
	if err := r.List(ctx, &list, client.InNamespace(s.Namespace)); err != nil {
		return false, "list sessions: " + err.Error()
	}
	residentYielded, otherSpots := false, 0
	for i := range list.Items {
		o := &list.Items[i]
		if o.Name == s.Name {
			continue
		}
		if o.Status.BoundGpuUuid == s.Spec.BorrowedGpuUuid &&
			(o.Status.YieldState == "Yielded" || o.Status.YieldState == "Lent") {
			residentYielded = true
		}
		if o.Spec.BorrowedGpuUuid == s.Spec.BorrowedGpuUuid && o.DeletionTimestamp.IsZero() {
			otherSpots++
		}
	}
	if !residentYielded {
		return false, "no yielded resident holds card " + s.Spec.BorrowedGpuUuid
	}
	if otherSpots > 0 {
		return false, "card " + s.Spec.BorrowedGpuUuid + " already lent to another spot session"
	}
	return true, ""
}

// setNodeYielded adds/removes gpuUUID in the node's gshare.io/yielded-gpus annotation (CSV) — the
// feed the HAMi scheduler-extender reads to treat the card as preemptible capacity. Best-effort,
// conflict-safe. (build/hami-fork, docs/paper/manuscript §Implementation)
func (r *SessionReconciler) setNodeYielded(ctx context.Context, nodeName, gpuUUID string, yielded bool) error {
	if nodeName == "" || gpuUUID == "" {
		return nil
	}
	return retry.RetryOnConflict(retry.DefaultRetry, func() error {
		var node corev1.Node
		if err := r.Get(ctx, types.NamespacedName{Name: nodeName}, &node); err != nil {
			return client.IgnoreNotFound(err)
		}
		set := map[string]struct{}{}
		for _, u := range strings.Split(node.Annotations[yieldedGPUsAnnotation], ",") {
			if u = strings.TrimSpace(u); u != "" {
				set[u] = struct{}{}
			}
		}
		if _, present := set[gpuUUID]; present == yielded {
			return nil // already in desired state
		}
		orig := node.DeepCopy()
		if yielded {
			set[gpuUUID] = struct{}{}
		} else {
			delete(set, gpuUUID)
		}
		uuids := make([]string, 0, len(set))
		for u := range set {
			uuids = append(uuids, u)
		}
		sort.Strings(uuids)
		if node.Annotations == nil {
			node.Annotations = map[string]string{}
		}
		if len(uuids) == 0 {
			delete(node.Annotations, yieldedGPUsAnnotation)
		} else {
			node.Annotations[yieldedGPUsAnnotation] = strings.Join(uuids, ",")
		}
		// Patch (not Update) — the operator holds nodes:patch (for cordon), not full update.
		return r.Patch(ctx, &node, client.MergeFrom(orig))
	})
}

// cleanupChildren deletes the session's child objects. Owner refs would garbage-collect
// them eventually; explicit deletion makes termination deterministic. NotFound is
// tolerated (already GC'd, or never created — e.g. cpu sessions have no Service/Ingress).
func (r *SessionReconciler) cleanupChildren(ctx context.Context, s *gsharev1.GShareSession) error {
	ns := s.Namespace
	if r.Builder != nil && r.Builder.Namespace != "" {
		ns = r.Builder.Namespace
	}

	children := []client.Object{
		&corev1.Pod{ObjectMeta: metav1.ObjectMeta{Namespace: ns, Name: "ses-" + s.Name}},
		&corev1.Service{ObjectMeta: metav1.ObjectMeta{Namespace: ns, Name: "ses-" + s.Name}},
		// Both per-session Ingress objects (apps + vscode).
		&netv1.Ingress{ObjectMeta: metav1.ObjectMeta{Namespace: ns, Name: "ses-" + s.Name + "-apps"}},
		&netv1.Ingress{ObjectMeta: metav1.ObjectMeta{Namespace: ns, Name: "ses-" + s.Name + "-vscode"}},
		&corev1.Secret{ObjectMeta: metav1.ObjectMeta{Namespace: ns, Name: "ses-" + s.Name + "-secret"}},
	}
	for _, obj := range children {
		var opts []client.DeleteOption
		if pod, ok := obj.(*corev1.Pod); ok && r.podNodeUnreachable(ctx, pod) {
			// The kubelet will never confirm the deletion; without a zero grace period the pod
			// sits in Terminating until someone deletes the Node object.
			opts = append(opts, client.GracePeriodSeconds(0))
		}
		if err := r.Delete(ctx, obj, opts...); err != nil && !apierrors.IsNotFound(err) {
			return err
		}
	}
	return nil
}

// ensureVolumeClaims creates a PVC per spec.volumes entry when missing (idempotent), and grows an
// existing one whose request is below spec.sizeGb — an approved quota increase reaching the claim
// at the next session start; the volume syncer does the same between sessions. Claims are never
// shrunk (a CSI cannot, and ZFS would not, safely). The PVC name is the sanitized volume id, the
// ledger id itself rides on an annotation, size comes from spec (10Gi default for older control
// planes), and the access mode is the volume's own class. Deliberately no ownerRef: the claim — and
// its data — must survive session teardown; volume deletion is a control-plane concern.
func (r *SessionReconciler) ensureVolumeClaims(ctx context.Context, s *gsharev1.GShareSession) error {
	for _, v := range s.Spec.Volumes {
		name := podbuilder.SanitizeVolumeName(v.Name)
		sizeGb := v.SizeGb
		if sizeGb <= 0 {
			sizeGb = 10
		}
		want := resource.MustParse(strconv.Itoa(sizeGb) + "Gi")
		var existing corev1.PersistentVolumeClaim
		err := r.Get(ctx, types.NamespacedName{Namespace: r.Builder.Namespace, Name: name}, &existing)
		if err == nil {
			if err := r.growClaim(ctx, &existing, want); err != nil {
				return err
			}
			continue
		}
		if !apierrors.IsNotFound(err) {
			return err
		}
		mode := corev1.PersistentVolumeAccessMode(v.Mode)
		pvc := &corev1.PersistentVolumeClaim{
			ObjectMeta: metav1.ObjectMeta{
				Namespace:   r.Builder.Namespace,
				Name:        name,
				Labels:      map[string]string{podbuilder.VolumeLabel: name},
				Annotations: map[string]string{podbuilder.VolumeIDAnnotation: v.Name},
			},
			Spec: corev1.PersistentVolumeClaimSpec{
				AccessModes: []corev1.PersistentVolumeAccessMode{mode},
				Resources: corev1.VolumeResourceRequirements{
					Requests: corev1.ResourceList{corev1.ResourceStorage: want},
				},
			},
		}
		if r.VolumeStorageClass != "" {
			pvc.Spec.StorageClassName = &r.VolumeStorageClass
		}
		if err := r.Create(ctx, pvc); err != nil && !apierrors.IsAlreadyExists(err) {
			return err
		}
	}
	return nil
}

// growClaim raises the PVC's storage request to want when it is currently smaller. A class
// without allowVolumeExpansion rejects the patch; that surfaces as a reconcile error rather than
// being hidden, since the user was promised the larger quota.
func (r *SessionReconciler) growClaim(ctx context.Context, pvc *corev1.PersistentVolumeClaim, want resource.Quantity) error {
	cur, ok := pvc.Spec.Resources.Requests[corev1.ResourceStorage]
	if ok && cur.Cmp(want) >= 0 {
		return nil
	}
	patch := client.MergeFrom(pvc.DeepCopy())
	if pvc.Spec.Resources.Requests == nil {
		pvc.Spec.Resources.Requests = corev1.ResourceList{}
	}
	pvc.Spec.Resources.Requests[corev1.ResourceStorage] = want
	return r.Patch(ctx, pvc, patch)
}

// applyIfAbsent creates obj if missing, otherwise no-ops (server-side apply later).
func (r *SessionReconciler) applyIfAbsent(ctx context.Context, obj client.Object) error {
	err := r.Create(ctx, obj)
	if apierrors.IsAlreadyExists(err) {
		return nil
	}
	return err
}

// podKey returns the NamespacedName of the session Pod.
func podKey(s *gsharev1.GShareSession) types.NamespacedName {
	return types.NamespacedName{Namespace: s.Namespace, Name: "ses-" + s.Name}
}

// mapPhase maps a Pod phase to a GShareSession phase. An absent Pod (empty UID) maps
// to Pending so the control plane holds the session rather than consuming or settling.
func mapPhase(p *corev1.Pod) string {
	if p == nil || p.UID == "" {
		return "Pending"
	}
	switch p.Status.Phase {
	case corev1.PodRunning:
		return "Running"
	case corev1.PodFailed:
		return "Error"
	case corev1.PodSucceeded:
		return "Terminated"
	case corev1.PodPending:
		return "Preparing"
	default:
		// Unknown phase: the Pod exists but is not yet observed — treat as Preparing.
		return "Preparing"
	}
}

// failureMessage joins a failed Pod's status Reason and Message as "Reason: Message",
// omitting the colon when either half is empty (both trimmed).
// evictionMessage returns "Evicted: <kubelet message>" when the kubelet recorded an Evicted
// event for the pod, and "" otherwise. Reader is the manager's API reader (uncached — events are
// not worth an informer). Nil-safe.
func evictionMessage(ctx context.Context, reader client.Reader, pod *corev1.Pod) string {
	if reader == nil || pod == nil || pod.Name == "" {
		return ""
	}
	var evs corev1.EventList
	if err := reader.List(ctx, &evs, client.InNamespace(pod.Namespace)); err != nil {
		return ""
	}
	for i := range evs.Items {
		e := &evs.Items[i]
		if e.Reason == "Evicted" && e.InvolvedObject.Kind == "Pod" && e.InvolvedObject.Name == pod.Name {
			return failureMessage(e.Reason, e.Message)
		}
	}
	return ""
}

func failureMessage(reason, message string) string {
	reason, message = strings.TrimSpace(reason), strings.TrimSpace(message)
	switch {
	case reason == "":
		return message
	case message == "":
		return reason
	}
	return reason + ": " + message
}

// boundGPU extracts the bound GPU UUID from the live Pod, tolerating absence (cpu
// sessions, exclusive sessions not yet scheduled, or a non-HAMi cluster).
func boundGPU(p *corev1.Pod) string {
	if p == nil {
		return ""
	}

	// HAMi records the allocated device(s) in a Pod annotation; take the first GPU UUID.
	for _, key := range hamiAllocatedAnnotations {
		if uuid := parseHamiDeviceUUID(p.Annotations[key]); uuid != "" {
			return uuid
		}
	}

	// Fallback: the device plugin / runtime exposes the bound device through
	// NVIDIA_VISIBLE_DEVICES on the session container (a UUID, or a comma list).
	for i := range p.Spec.Containers {
		c := &p.Spec.Containers[i]
		for _, e := range c.Env {
			if e.Name == "NVIDIA_VISIBLE_DEVICES" {
				if uuid := firstGPUUUID(e.Value); uuid != "" {
					return uuid
				}
			}
		}
	}
	return ""
}

// hamiAllocatedAnnotations are the Pod annotation keys HAMi records bound device(s) in,
// tried in order: "-allocated" (set after binding), then "-to-allocate" (pre-bind hint).
var hamiAllocatedAnnotations = []string{
	"hami.io/vgpu-devices-allocated",
	"hami.io/vgpu-devices-to-allocate",
}

// parseHamiDeviceUUID extracts the first GPU UUID from a HAMi device-allocation
// annotation value. HAMi encodes each device as "<uuid>,<type>,<mem>,<cores>" with ":"
// within a device and ";" / ":;" between devices; the UUID is the leading token.
func parseHamiDeviceUUID(v string) string {
	if v == "" {
		return ""
	}
	// Normalize the HAMi separators to one, then take the first record.
	v = strings.NewReplacer(":;", ";", ":", ";").Replace(v)
	for _, rec := range strings.Split(v, ";") {
		rec = strings.TrimSpace(rec)
		if rec == "" {
			continue
		}
		field := rec
		if i := strings.IndexByte(rec, ','); i >= 0 {
			field = rec[:i]
		}
		if uuid := normalizeGPUUUID(field); uuid != "" {
			return uuid
		}
	}
	return ""
}

// firstGPUUUID returns the first GPU UUID from a NVIDIA_VISIBLE_DEVICES value
// (which may be "all", "none", an index list, or a comma-separated UUID list).
func firstGPUUUID(v string) string {
	for _, tok := range strings.Split(v, ",") {
		if uuid := normalizeGPUUUID(strings.TrimSpace(tok)); uuid != "" {
			return uuid
		}
	}
	return ""
}

// normalizeGPUUUID returns tok if it looks like a real GPU UUID ("GPU-..." form),
// otherwise "". Sentinels ("all"/"none"/"void"/empty) and bare integer indices are
// rejected so we never report a non-UUID as the bound device.
func normalizeGPUUUID(tok string) string {
	// MIG- accepted defensively: env-fallback discovery on a MIG-partitioned card can surface a
	// MIG instance UUID; rejecting it would blank BoundGpuUuid and break the reaper's util lookup.
	if !strings.HasPrefix(tok, "GPU-") && !strings.HasPrefix(tok, "MIG-") {
		return ""
	}
	if len(tok) <= len("GPU-") {
		return ""
	}
	return tok
}

// traceIDFromAnnotations extracts the trace-id from a W3C traceparent annotation
// ("version-traceid-parentid-flags", widths 2-32-16-2 hex). Malformed -> "".
func traceIDFromAnnotations(ann map[string]string) string {
	if ann == nil {
		return ""
	}
	tp := strings.TrimSpace(ann[traceparentAnnotation])
	if tp == "" {
		return ""
	}
	parts := strings.Split(tp, "-")
	if len(parts) != 4 {
		return ""
	}
	version, traceID, parentID, flags := parts[0], parts[1], parts[2], parts[3]
	// version 0xff is forbidden by the spec.
	if !isHex(version, 2) || version == "ff" ||
		!isHex(traceID, 32) || isAllZero(traceID) ||
		!isHex(parentID, 16) || isAllZero(parentID) ||
		!isHex(flags, 2) {
		return ""
	}
	return traceID
}

// isHex reports whether s is exactly n lowercase-hex characters.
func isHex(s string, n int) bool {
	if len(s) != n {
		return false
	}
	for i := 0; i < len(s); i++ {
		c := s[i]
		if !((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f')) {
			return false
		}
	}
	return true
}

// isAllZero reports whether s is all '0' characters (an invalid trace/parent id).
func isAllZero(s string) bool {
	for i := 0; i < len(s); i++ {
		if s[i] != '0' {
			return false
		}
	}
	return len(s) > 0
}

// SetupWithManager registers the controller with the manager.
func (r *SessionReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&gsharev1.GShareSession{}).
		Owns(&corev1.Pod{}).
		Owns(&corev1.Service{}).
		Owns(&corev1.Secret{}).
		Owns(&netv1.Ingress{}).
		Complete(r)
}

// podNodeUnreachable reports whether the pod's node has stopped answering (Ready != True), in
// which case a graceful delete can never complete.
func (r *SessionReconciler) podNodeUnreachable(ctx context.Context, key *corev1.Pod) bool {
	var live corev1.Pod
	if err := r.Get(ctx, client.ObjectKeyFromObject(key), &live); err != nil || live.Spec.NodeName == "" {
		return false
	}
	var node corev1.Node
	if err := r.Get(ctx, client.ObjectKey{Name: live.Spec.NodeName}, &node); err != nil {
		return false
	}
	for _, c := range node.Status.Conditions {
		if c.Type == corev1.NodeReady {
			return c.Status != corev1.ConditionTrue
		}
	}
	return true
}

// nodeExcluded reports whether a pod on `hostname` must be moved: the control plane listed the
// node in spec.excludedNodes AND the node is currently unschedulable (the mirrored cordon) or
// not Ready. The second condition is what keeps a stale list harmless: once the cordon is lifted
// a pod landing there is fine and must not be churned.
func (r *SessionReconciler) nodeExcluded(ctx context.Context, hostname string, excluded []string) bool {
	listed := false
	for _, h := range excluded {
		if h == hostname {
			listed = true
			break
		}
	}
	if !listed {
		return false
	}
	var node corev1.Node
	if err := r.Get(ctx, client.ObjectKey{Name: hostname}, &node); err != nil {
		return false
	}
	if node.Spec.Unschedulable {
		return true
	}
	for _, c := range node.Status.Conditions {
		if c.Type == corev1.NodeReady {
			return c.Status != corev1.ConditionTrue
		}
	}
	return false
}
