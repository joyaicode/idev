// Package local is the single-machine wiring: a file signing key, the people
// whitelist as the authorizer, and the person's local credential.
//
// Assurance is `low` by construction (design §10.4, threat T4). Everything
// here lives under the data directory, which a process running as the same
// user can read; what an agent cannot do is answer from a terminal it does
// not have, and that is the barrier the CLI enforces.
package local

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"go.yaml.in/yaml/v3"

	"github.com/idev/internal/domain/signoff"
	"github.com/idev/internal/domain/ulid"
	"github.com/idev/internal/ports"
)

// DataDir is where the database and secrets live: $IDEV_DATA, else ~/.idev.
// Outside every checkout on purpose, so a key cannot be committed.
func DataDir() (string, error) {
	if d := strings.TrimSpace(os.Getenv("IDEV_DATA")); d != "" {
		return d, nil
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return "", fmt.Errorf("local: no home directory and IDEV_DATA unset: %w", err)
	}
	return filepath.Join(home, ".idev"), nil
}

// --- signer ------------------------------------------------------------------

// Signer signs with one Ed25519 key kept in a 0600 file.
type Signer struct {
	priv  ed25519.PrivateKey
	keyID string
}

// LoadOrCreateSigner reads the key at path, creating it on first use.
func LoadOrCreateSigner(path string) (*Signer, error) {
	raw, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) {
		_, priv, gerr := ed25519.GenerateKey(rand.Reader)
		if gerr != nil {
			return nil, fmt.Errorf("local: generating signing key: %w", gerr)
		}
		if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
			return nil, err
		}
		if err := os.WriteFile(path, []byte(hex.EncodeToString(priv.Seed())), 0o600); err != nil {
			return nil, fmt.Errorf("local: writing signing key: %w", err)
		}
		return newSigner(priv), nil
	}
	if err != nil {
		return nil, fmt.Errorf("local: reading signing key: %w", err)
	}
	seed, err := hex.DecodeString(strings.TrimSpace(string(raw)))
	if err != nil || len(seed) != ed25519.SeedSize {
		return nil, fmt.Errorf("local: %s is not an ed25519 seed", path)
	}
	return newSigner(ed25519.NewKeyFromSeed(seed)), nil
}

func newSigner(priv ed25519.PrivateKey) *Signer {
	sum := sha256.Sum256(priv.Public().(ed25519.PublicKey))
	return &Signer{priv: priv, keyID: "local-" + hex.EncodeToString(sum[:8])}
}

func (s *Signer) Sign(_ context.Context, payload []byte) ([]byte, string, error) {
	return ed25519.Sign(s.priv, payload), s.keyID, nil
}

func (s *Signer) Verify(_ context.Context, payload, sig []byte, keyID string) error {
	if keyID != s.keyID {
		return fmt.Errorf("local: signed by %s, this machine's key is %s", keyID, s.keyID)
	}
	if !ed25519.Verify(s.priv.Public().(ed25519.PublicKey), payload, sig) {
		return errors.New("local: signature does not verify")
	}
	return nil
}

func (s *Signer) KeyID(context.Context) (string, error) { return s.keyID, nil }

// --- authorizer --------------------------------------------------------------

// People answers gate.approve from the people whitelist. Blacklist-only is
// refused, as workflow.py refuses it: a plausible invented name must not be
// able to sign.
type People struct {
	Identity signoff.Identity
}

func (p People) Can(_ context.Context, pr ports.Principal, action, _ string) bool {
	if action != "gate.approve" || pr.Kind != "human" {
		return false
	}
	if len(p.Identity.Whitelist) == 0 {
		return false
	}
	return p.Identity.IsHuman(pr.Handle)
}

// LoadPeople unions every people.yaml that exists among paths. An unreadable
// file is an error, not an empty list: that would be more permissive than
// the person intended.
func LoadPeople(paths []string) (signoff.Identity, []string, error) {
	names := map[string]bool{}
	var used []string
	for _, path := range paths {
		raw, err := os.ReadFile(path)
		if errors.Is(err, os.ErrNotExist) {
			continue
		}
		if err != nil {
			return signoff.Identity{}, nil, err
		}
		var doc struct {
			People []string `yaml:"people"`
		}
		if err := yaml.Unmarshal(raw, &doc); err != nil {
			return signoff.Identity{}, nil, fmt.Errorf("local: %s: %w", path, err)
		}
		for _, n := range doc.People {
			if n = strings.ToLower(strings.TrimSpace(n)); n != "" {
				names[n] = true
			}
		}
		used = append(used, path)
	}
	return signoff.Identity{Whitelist: names}, used, nil
}

// --- the person's credential -------------------------------------------------

// TokenPrefix marks a local human token (design §10.4).
const TokenPrefix = "idv_h_"

// Credential is who answers from this machine.
type Credential struct {
	Handle string `yaml:"handle"`
	Token  string `yaml:"token"`
}

// Principal is the authenticated caller this credential stands for. Kind is
// human because the credential is only usable from a terminal; the whitelist
// still decides whether the handle may sign.
func (c Credential) Principal() ports.Principal {
	sum := sha256.Sum256([]byte(c.Token))
	return ports.Principal{ID: "local:" + hex.EncodeToString(sum[:6]), Handle: c.Handle, Kind: "human"}
}

// WriteCredential creates the credential file, refusing to overwrite one.
func WriteCredential(path, handle string) (Credential, error) {
	if _, err := os.Stat(path); err == nil {
		return Credential{}, fmt.Errorf("local: %s already exists; remove it yourself to re-issue", path)
	}
	buf := make([]byte, 24)
	if _, err := rand.Read(buf); err != nil {
		return Credential{}, err
	}
	c := Credential{Handle: strings.TrimSpace(handle), Token: TokenPrefix + hex.EncodeToString(buf)}
	raw, err := yaml.Marshal(c)
	if err != nil {
		return Credential{}, err
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return Credential{}, err
	}
	return c, os.WriteFile(path, raw, 0o600)
}

// ReadCredential loads the credential, refusing one that others can read.
func ReadCredential(path string) (Credential, error) {
	info, err := os.Stat(path)
	if err != nil {
		return Credential{}, fmt.Errorf("local: no credential at %s; run `idev token init --handle <you>` in your terminal", path)
	}
	if info.Mode().Perm()&0o077 != 0 {
		return Credential{}, fmt.Errorf("local: %s is readable by others (%v); chmod 600 it", path, info.Mode().Perm())
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		return Credential{}, err
	}
	var c Credential
	if err := yaml.Unmarshal(raw, &c); err != nil {
		return Credential{}, fmt.Errorf("local: %s: %w", path, err)
	}
	if c.Handle == "" || !strings.HasPrefix(c.Token, TokenPrefix) {
		return Credential{}, fmt.Errorf("local: %s has no handle or no %s token", path, TokenPrefix)
	}
	return c, nil
}

// --- clock and ids -----------------------------------------------------------

type Clock struct{}

func (Clock) Now() time.Time { return time.Now().UTC() }

type IDs struct{}

func (IDs) New() string {
	id, err := ulid.NewAt(time.Now())
	if err != nil {
		panic(fmt.Sprintf("local: ulid: %v", err))
	}
	return id
}
