package sampler

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"
)

// Pusher posts sample batches to the control plane's internal ingest endpoint.
//
// It holds a short-lived internal JWT the same way the operator does: the token is read from disk
// on every request, because the control plane rotates it in place and a cached copy would start
// failing after the rotation.
type Pusher struct {
	BaseURL   string
	TokenFile string
	Node      string
	Client    *http.Client
}

func NewPusher(baseURL, tokenFile, node string) *Pusher {
	return &Pusher{
		BaseURL:   strings.TrimRight(baseURL, "/"),
		TokenFile: tokenFile,
		Node:      node,
		Client:    &http.Client{Timeout: 5 * time.Second},
	}
}

type report struct {
	Node    string   `json:"node"`
	Samples []Sample `json:"samples"`
}

func (p *Pusher) Push(ctx context.Context, samples []Sample) error {
	body, err := json.Marshal(report{Node: p.Node, Samples: samples})
	if err != nil {
		return err
	}
	token, err := p.token()
	if err != nil {
		return err
	}
	url := p.BaseURL + "/internal/metrics/session-samples"
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+token)
	resp, err := p.Client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		msg, _ := io.ReadAll(io.LimitReader(resp.Body, 512))
		return fmt.Errorf("ingest %s: %s", resp.Status, strings.TrimSpace(string(msg)))
	}
	_, _ = io.Copy(io.Discard, resp.Body)
	return nil
}

func (p *Pusher) token() (string, error) {
	b, err := os.ReadFile(p.TokenFile)
	if err != nil {
		return "", fmt.Errorf("read internal token: %w", err)
	}
	t := strings.TrimSpace(string(b))
	if t == "" {
		return "", fmt.Errorf("internal token file %s is empty", p.TokenFile)
	}
	return t, nil
}
