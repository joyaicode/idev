// Command idev is the local gate channel: an agent asks, and the person's
// words in the conversation are the answer. The driver records that quote.
// It does not ask for a terminal or a short code.
//
//	idev gate request --feature F --type T --risk P1 [--run-id R --step S]
//	                  [--root DIR --subject PATH ...] [--revision N] [--origin O]
//	                  [--will-write W ...] [--proof P]
//	idev gate approve <id> --quote Q      # the person's words of agreement
//	idev gate reject  <id> --quote Q      # the person's 驳回
//	idev gate status  <id>                 # JSON, for workflow.py
//	idev lease acquire --run R --step S [--purpose write|verify] [--ticket-dir D] ... # JSON, for workflow.py
//	idev lease release <id> --token T
//	idev lease check   <id> [--path P ...] # JSON
//	idev audit downgrades                  # JSON, high asks answered at low, per ISO week
//	idev audit export [--run ID] [--out F] # JSONL audit chain (read-only export)
//	idev workspace locate|manifest|diff|head
//	idev token init --handle H             # once, in a terminal
//
// Assurance is low (design §10.4): the data directory is readable by any
// process running as the person, so a determined forgery is out of scope.
// What the quote check stops is the common failure — an agent recording a
// signature the person did not say. When prompts.log is active, the quote
// has to be in it.
package main

import (
	"os"

	"github.com/mattn/go-isatty"
)

func main() {
	a := app{
		stdin:  os.Stdin,
		stdout: os.Stdout,
		stderr: os.Stderr,
		isTTY: func() bool {
			return isatty.IsTerminal(os.Stdin.Fd()) && isatty.IsTerminal(os.Stdout.Fd())
		},
	}
	os.Exit(a.run(os.Args[1:]))
}
