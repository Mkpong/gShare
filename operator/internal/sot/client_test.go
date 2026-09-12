/*
SoT client tests: retry on 5xx / transport errors, no retry on 4xx, 409 as success, the
short-lived token being re-read (and its expiry honoured) on every attempt.
*/
package sot

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

// unsignedJWT builds a header.payload.signature string whose payload carries exp; the client
// never verifies, it only reads the claim.
func unsignedJWT(exp time.Time) string {
	hdr := base64.RawURLEncoding.EncodeToString([]byte(`{"alg":"RS256","kid":"t"}`))
	payload, _ := json.Marshal(map[string]any{"sub": "operator:clu_test", "exp": exp.Unix()})
	return hdr + "." + base64.RawURLEncoding.EncodeToString(payload) + ".sig"
}

func tokenFile(t *testing.T, token string) string {
	t.Helper()
	p := filepath.Join(t.TempDir(), "internal-jwt")
	if err := os.WriteFile(p, []byte(token+"\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	return p
}

type capture struct {
	calls  atomic.Int32
	auth   string
	path   string
	body   map[string]any
	trace  string
	status []int // per-attempt status codes; the last one repeats
}

func (c *capture) handler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		n := int(c.calls.Add(1)) - 1
		c.auth = r.Header.Get("Authorization")
		c.path = r.URL.Path
		c.trace = r.Header.Get("traceparent")
		var body map[string]any
		_ = json.NewDecoder(r.Body).Decode(&body)
		c.body = body
		code := c.status[len(c.status)-1]
		if n < len(c.status) {
			code = c.status[n]
		}
		w.WriteHeader(code)
		_, _ = fmt.Fprint(w, `{"accepted":true}`)
	}
}

func newClient(t *testing.T, srv *httptest.Server, token string) *Client {
	t.Helper()
	return New(Config{
		BaseURL:     srv.URL,
		StatusPath:  "/internal/sessions/{id}/status",
		AuditPath:   "/internal/audit/operator",
		TokenFile:   tokenFile(t, token),
		ClusterID:   "clu_test",
		HTTPTimeout: 2 * time.Second,
	})
}

func TestReportRetriesServerErrorsThenSucceeds(t *testing.T) {
	cap := &capture{status: []int{503, 500, 202}}
	srv := httptest.NewServer(cap.handler())
	defer srv.Close()
	token := unsignedJWT(time.Now().Add(time.Hour))
	c := newClient(t, srv, token)

	err := c.Report(context.Background(), "ses-01abc", StatusEvent{Phase: "Running", Generation: 3,
		TraceID: "4bf92f3577b34da6a3ce929d0e0e4736"})
	if err != nil {
		t.Fatalf("expected success after retries, got %v", err)
	}
	if got := cap.calls.Load(); got != 3 {
		t.Fatalf("expected 3 attempts (2 failures + success), got %d", got)
	}
	if cap.auth != "Bearer "+token {
		t.Fatalf("bearer token not sent verbatim: %q", cap.auth)
	}
	if cap.path != "/internal/sessions/ses-01abc/status" {
		t.Fatalf("status path template not rendered: %q", cap.path)
	}
	if cap.body["phase"] != "Running" || cap.body["cluster_id"] != "clu_test" || cap.body["generation"] != float64(3) {
		t.Fatalf("payload mismatch: %v", cap.body)
	}
	if _, ok := cap.body["ts"]; !ok {
		t.Fatalf("ts must be filled when zero: %v", cap.body)
	}
	if !strings.HasPrefix(cap.trace, "00-4bf92f3577b34da6a3ce929d0e0e4736-") {
		t.Fatalf("traceparent not propagated: %q", cap.trace)
	}
}

func TestReportDoesNotRetryClientErrors(t *testing.T) {
	// 401 is deliberately absent: it is the one 4xx a token rotation can cause, and it has its
	// own retry-exactly-once tests below.
	for _, code := range []int{400, 403, 422} {
		cap := &capture{status: []int{code}}
		srv := httptest.NewServer(cap.handler())
		c := newClient(t, srv, unsignedJWT(time.Now().Add(time.Hour)))
		err := c.Report(context.Background(), "s", StatusEvent{Phase: "Running"})
		srv.Close()
		if err == nil {
			t.Fatalf("%d must be an error", code)
		}
		if cap.calls.Load() != 1 {
			t.Fatalf("%d must not be retried, got %d attempts", code, cap.calls.Load())
		}
	}
}

func TestConflictIsIdempotentSuccess(t *testing.T) {
	cap := &capture{status: []int{409}}
	srv := httptest.NewServer(cap.handler())
	defer srv.Close()
	c := newClient(t, srv, unsignedJWT(time.Now().Add(time.Hour)))
	if err := c.Report(context.Background(), "s", StatusEvent{Phase: "Terminated"}); err != nil {
		t.Fatalf("409 must be treated as already applied, got %v", err)
	}
}

func TestReportGivesUpAfterMaxAttempts(t *testing.T) {
	cap := &capture{status: []int{500}}
	srv := httptest.NewServer(cap.handler())
	defer srv.Close()
	c := newClient(t, srv, unsignedJWT(time.Now().Add(time.Hour)))
	err := c.Report(context.Background(), "s", StatusEvent{Phase: "Terminated"})
	if err == nil || !strings.Contains(err.Error(), "status 500") {
		t.Fatalf("expected the last 5xx to surface, got %v", err)
	}
	if cap.calls.Load() != maxAttempts {
		t.Fatalf("expected %d attempts, got %d", maxAttempts, cap.calls.Load())
	}
}

func TestExpiredTokenIsNotSentAndRotationIsPickedUp(t *testing.T) {
	cap := &capture{status: []int{202}}
	srv := httptest.NewServer(cap.handler())
	defer srv.Close()
	c := newClient(t, srv, unsignedJWT(time.Now().Add(-time.Minute)))

	err := c.Report(context.Background(), "s", StatusEvent{Phase: "Running"})
	if err == nil || !strings.Contains(err.Error(), "expired") {
		t.Fatalf("an expired token must surface as an error, got %v", err)
	}
	if cap.calls.Load() != 0 {
		t.Fatalf("an expired token must never reach the wire, got %d calls", cap.calls.Load())
	}

	// The control plane rotates the file; the next report picks it up without a restart.
	fresh := unsignedJWT(time.Now().Add(time.Hour))
	if err := os.WriteFile(c.cfg.TokenFile, []byte(fresh), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := c.Report(context.Background(), "s", StatusEvent{Phase: "Running"}); err != nil {
		t.Fatalf("rotated token must be used, got %v", err)
	}
	if cap.auth != "Bearer "+fresh {
		t.Fatalf("rotated token not sent: %q", cap.auth)
	}
}

func TestTokenIsReReadOnEveryAttempt(t *testing.T) {
	// First attempt fails with 500; the token file is rotated in between; the retry must carry
	// the new token.
	var seen []string
	first := unsignedJWT(time.Now().Add(time.Hour))
	second := unsignedJWT(time.Now().Add(2 * time.Hour))
	var path string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		seen = append(seen, r.Header.Get("Authorization"))
		if len(seen) == 1 {
			_ = os.WriteFile(path, []byte(second), 0o600)
			w.WriteHeader(500)
			return
		}
		w.WriteHeader(202)
	}))
	defer srv.Close()
	c := newClient(t, srv, first)
	path = c.cfg.TokenFile
	if err := c.Report(context.Background(), "s", StatusEvent{Phase: "Running"}); err != nil {
		t.Fatal(err)
	}
	if len(seen) != 2 || seen[0] != "Bearer "+first || seen[1] != "Bearer "+second {
		t.Fatalf("expected the retry to carry the rotated token, got %v", seen)
	}
}

func TestEmptyOrMissingTokenFile(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(202) }))
	defer srv.Close()
	c := newClient(t, srv, "")
	if err := c.Report(context.Background(), "s", StatusEvent{Phase: "Running"}); err == nil || !strings.Contains(err.Error(), "empty internal JWT") {
		t.Fatalf("empty token file must error, got %v", err)
	}
	c.cfg.TokenFile = filepath.Join(t.TempDir(), "missing")
	if err := c.Report(context.Background(), "s", StatusEvent{Phase: "Running"}); err == nil {
		t.Fatalf("missing token file must error")
	}
}

func TestContextCancelStopsTheBackoff(t *testing.T) {
	cap := &capture{status: []int{500}}
	srv := httptest.NewServer(cap.handler())
	defer srv.Close()
	c := newClient(t, srv, unsignedJWT(time.Now().Add(time.Hour)))
	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()
	start := time.Now()
	err := c.Report(ctx, "s", StatusEvent{Phase: "Running"})
	if err == nil {
		t.Fatalf("expected an error")
	}
	if time.Since(start) > time.Second {
		t.Fatalf("cancelled context must cut the backoff short, took %v", time.Since(start))
	}
}

func TestTokenExpiryParsing(t *testing.T) {
	exp := time.Now().Add(time.Hour).Truncate(time.Second)
	if got, ok := tokenExpiry(unsignedJWT(exp)); !ok || !got.Equal(exp) {
		t.Fatalf("expected exp %v, got %v ok=%v", exp, got, ok)
	}
	for _, bad := range []string{"", "a.b", "a.!!!.c", "a." + base64.RawURLEncoding.EncodeToString([]byte(`{"sub":"x"}`)) + ".c"} {
		if _, ok := tokenExpiry(bad); ok {
			t.Fatalf("%q must not parse an expiry", bad)
		}
	}
}

// ── GS-C11: a 401 is retried exactly once with a freshly read token ──

func TestUnauthorizedIsRetriedOnceWithARereadToken(t *testing.T) {
	// The control plane rotates the token file under the operator, and its JWKS cache can lag a
	// key rotation: the 401 here is a report racing a rotation, not a report that can never be
	// accepted. Dropping it lost a Running/Paused report, which has no other retry path.
	var seen []string
	first := unsignedJWT(time.Now().Add(time.Hour))
	second := unsignedJWT(time.Now().Add(2 * time.Hour))
	var path string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		seen = append(seen, r.Header.Get("Authorization"))
		if len(seen) == 1 {
			_ = os.WriteFile(path, []byte(second), 0o600)
			w.WriteHeader(401)
			return
		}
		w.WriteHeader(202)
	}))
	defer srv.Close()
	c := newClient(t, srv, first)
	path = c.cfg.TokenFile

	if err := c.Report(context.Background(), "s", StatusEvent{Phase: "Running"}); err != nil {
		t.Fatalf("a 401 followed by a 202 must end as one successful report, got %v", err)
	}
	if len(seen) != 2 {
		t.Fatalf("expected exactly 2 attempts (401 then 202), got %d: %v", len(seen), seen)
	}
	if seen[0] != "Bearer "+first || seen[1] != "Bearer "+second {
		t.Fatalf("the retry must carry the re-read token, got %v", seen)
	}
}

func TestUnauthorizedIsRetriedAtMostOnce(t *testing.T) {
	cap := &capture{status: []int{401}}
	srv := httptest.NewServer(cap.handler())
	defer srv.Close()
	c := newClient(t, srv, unsignedJWT(time.Now().Add(time.Hour)))
	err := c.Report(context.Background(), "s", StatusEvent{Phase: "Running"})
	if err == nil || !strings.Contains(err.Error(), "status 401") {
		t.Fatalf("a persistent 401 must surface, got %v", err)
	}
	if cap.calls.Load() != 2 {
		t.Fatalf("a 401 must be retried exactly once (2 attempts), got %d", cap.calls.Load())
	}
}

func TestForbiddenIsNeverRetried(t *testing.T) {
	cap := &capture{status: []int{403}}
	srv := httptest.NewServer(cap.handler())
	defer srv.Close()
	c := newClient(t, srv, unsignedJWT(time.Now().Add(time.Hour)))
	if err := c.Report(context.Background(), "s", StatusEvent{Phase: "Running"}); err == nil {
		t.Fatalf("403 must be an error")
	}
	if cap.calls.Load() != 1 {
		t.Fatalf("403 (wrong cluster, revoked scope) must not be retried, got %d attempts", cap.calls.Load())
	}
}

// ── GS-C12: "no restarts" and "not reported" are different facts ──

func TestRestartCountZeroIsTransmitted(t *testing.T) {
	zero := 0
	raw, err := json.Marshal(StatusEvent{Phase: "Running", RestartCount: &zero})
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(raw), `"restart_count":0`) {
		t.Fatalf("a pod that has never restarted must report 0, got %s", raw)
	}
	// Nil stays off the wire: a report with no pod behind it must not claim zero restarts.
	raw, err = json.Marshal(StatusEvent{Phase: "Terminated"})
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(raw), "restart_count") {
		t.Fatalf("an unknown restart count must be omitted, got %s", raw)
	}
}

func TestReportSendsRestartCountZeroOverTheWire(t *testing.T) {
	cap := &capture{status: []int{202}}
	srv := httptest.NewServer(cap.handler())
	defer srv.Close()
	c := newClient(t, srv, unsignedJWT(time.Now().Add(time.Hour)))
	zero := 0
	if err := c.Report(context.Background(), "s", StatusEvent{Phase: "Running", RestartCount: &zero}); err != nil {
		t.Fatal(err)
	}
	got, ok := cap.body["restart_count"]
	if !ok || got != float64(0) {
		t.Fatalf("restart_count 0 must reach the control plane, got %v (present=%v)", got, ok)
	}
}
