// Package sampler reads per-session resource use straight from the kernel's cgroup v2 files.
//
// Why not Prometheus: cAdvisor aggregates on its own ~10 s housekeeping cycle, so no scrape
// interval brings a reading below that. The cgroup files are the counters cAdvisor itself reads,
// and they are exact at the instant they are opened — which is what makes a one-second view of a
// session honest rather than smoothed.
package sampler

import (
	"bufio"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

// Root is the mount point of the host's cgroup v2 hierarchy inside the agent container.
var Root = "/sys/fs/cgroup"

// PodPath returns the cgroup directory of one pod.
//
// systemd-driver kubelets nest by QoS class: Guaranteed pods sit directly under kubepods.slice,
// while Burstable and BestEffort get a class slice of their own. The UID's dashes become
// underscores in the slice name. The cgroupfs driver uses a flat directory layout instead, so both
// shapes are tried and the first that exists wins.
func PodPath(uid, qosClass string) (string, error) {
	u := strings.ReplaceAll(uid, "-", "_")
	qos := strings.ToLower(qosClass)
	candidates := []string{}
	switch qos {
	case "burstable", "besteffort":
		candidates = append(candidates, filepath.Join(Root, "kubepods.slice",
			fmt.Sprintf("kubepods-%s.slice", qos), fmt.Sprintf("kubepods-%s-pod%s.slice", qos, u)))
	default:
		candidates = append(candidates, filepath.Join(Root, "kubepods.slice",
			fmt.Sprintf("kubepods-pod%s.slice", u)))
	}
	// cgroupfs driver, and the QoS-less fallback for either driver.
	if qos == "burstable" || qos == "besteffort" {
		candidates = append(candidates, filepath.Join(Root, "kubepods", qos, "pod"+uid))
	}
	candidates = append(candidates,
		filepath.Join(Root, "kubepods", "pod"+uid),
		filepath.Join(Root, "kubepods.slice", fmt.Sprintf("kubepods-pod%s.slice", u)),
	)
	for _, c := range candidates {
		if st, err := os.Stat(c); err == nil && st.IsDir() {
			return c, nil
		}
	}
	return "", fmt.Errorf("cgroup for pod %s (qos %s) not found under %s", uid, qosClass, Root)
}

// Reading is one sample of a pod's cgroup: a cumulative CPU counter and the memory in use now.
type Reading struct {
	CPUUsageUsec uint64
	MemBytes     uint64
	MemMaxBytes  uint64 // 0 when the cgroup sets no limit ("max")
}

// Read takes one sample. Missing files are not fatal on their own — a pod that exits between the
// listing and the read simply yields an error the caller drops.
func Read(dir string) (Reading, error) {
	var r Reading
	usage, err := cpuUsageUsec(filepath.Join(dir, "cpu.stat"))
	if err != nil {
		return r, err
	}
	r.CPUUsageUsec = usage
	if v, err := readUint(filepath.Join(dir, "memory.current")); err == nil {
		r.MemBytes = v
	}
	if v, err := readUint(filepath.Join(dir, "memory.max")); err == nil {
		r.MemMaxBytes = v
	}
	return r, nil
}

func cpuUsageUsec(path string) (uint64, error) {
	f, err := os.Open(path)
	if err != nil {
		return 0, err
	}
	defer f.Close()
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		fields := strings.Fields(sc.Text())
		if len(fields) == 2 && fields[0] == "usage_usec" {
			return strconv.ParseUint(fields[1], 10, 64)
		}
	}
	return 0, fmt.Errorf("usage_usec missing in %s", path)
}

// readUint reads a single-value cgroup file. "max" means no limit and reads as 0.
func readUint(path string) (uint64, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return 0, err
	}
	s := strings.TrimSpace(string(b))
	if s == "max" {
		return 0, nil
	}
	return strconv.ParseUint(s, 10, 64)
}
