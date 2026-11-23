// A bounded local transport for the official Gitleaks library, not new rules.
package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"io"
	"os"
	"runtime"
	"time"

	"github.com/rs/zerolog"
	"github.com/zricethezav/gitleaks/v8/config"
	"github.com/zricethezav/gitleaks/v8/detect"
	"github.com/zricethezav/gitleaks/v8/regexp"
	"github.com/zricethezav/gitleaks/v8/sources"
)

const maxInput = 512 * 1024 * 1024

func scan(payload []byte, cfg config.Config) byte {
	ctx, cancel := context.WithTimeout(context.Background(), 8*time.Second)
	defer cancel()
	// Reuse compiled immutable rules, but never findings or request state.
	d := detect.NewDetectorContext(ctx, cfg)
	d.Redact = 100
	d.IgnoreGitleaksAllow = true
	d.MaxDecodeDepth = 2
	d.MaxArchiveDepth = 0
	findings, err := d.DetectSource(ctx, &sources.File{Content: bytes.NewReader(payload), MaxArchiveDepth: 0})
	if err != nil || ctx.Err() != nil {
		return 2
	}
	if len(findings) != 0 {
		return 1
	}
	return 0
}

func main() {
	zerolog.SetGlobalLevel(zerolog.Disabled)
	seed, err := detect.NewDetectorDefaultConfig()
	if err != nil {
		os.Exit(2)
	}
	cfg := seed.Config
	digest := sha256.Sum256([]byte(config.DefaultConfig))
	hello := map[string]string{"format": "geneloop.gitleaks-worker/v1", "gitleaks": "8.30.0", "rules_sha256": hex.EncodeToString(digest[:]), "regex_engine": regexp.Version}
	if json.NewEncoder(os.Stdout).Encode(hello) != nil {
		os.Exit(2)
	}
	for {
		var size uint64
		err := binary.Read(os.Stdin, binary.BigEndian, &size)
		if err == io.EOF {
			return
		}
		if err != nil || size > maxInput {
			os.Exit(2)
		}
		payload := make([]byte, int(size))
		if _, err = io.ReadFull(os.Stdin, payload); err != nil {
			os.Exit(2)
		}
		status := scan(payload, cfg)
		clear(payload)
		payload = nil
		// Findings are unreachable after scan; retain no request results in the worker.
		runtime.GC()
		if _, err = os.Stdout.Write([]byte{status}); err != nil {
			return
		}
	}
}
