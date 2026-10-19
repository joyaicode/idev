// Command idev is the local gate channel: an agent asks, a person answers
// from their own terminal, and the answer is a signed record the driver reads
// back instead of a name the agent typed.
//
//	idev gate request --feature F --type T --risk P1 [--run-id R --step S]
//	                  [--root DIR --subject PATH ...] [--revision N] [--origin O]
//	                  [--will-write W ...] [--proof P]
//	idev gate approve <id> [--quote Q]     # a person, in a terminal
//	idev gate reject  <id> [--quote Q]     # a person, in a terminal
//	idev gate status  <id>                 # JSON, for workflow.py
//	idev token init --handle H             # once, in a terminal
//
// Assurance is low (design §10.4): the data directory is readable by any
// process running as the person, so a determined forgery is out of scope.
// What the terminal check stops is the common failure — an agent recording a
// signature nobody gave.
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
