# Pilot report: canonical/lxd#15874 "disk propagation not working"

Local only. Nothing was pushed or proposed upstream. LXD base: `02ae75e5df`; fix branch `fix-15874-disk-propagation` in
`~/git/lxd/.claude/worktrees/repro-15874`.

## Outcome
`propagation=rshared` on a disk device now works. A tmpfs mounted inside a privileged or unprivileged container reaches the host;
the default (no `propagation`) is unchanged. Root cause: `DiskMount` OR-ed the propagation flags into the same `mount(2)` call as
`MS_BIND` (the kernel ignores them) and then always forced `MS_REC|MS_SLAVE`.

## Gate results (`pilots/lxd-15874/gauntlet.toml`: CRAP max 8, mutation min 90, 7 layers)
| Gate | Before (main) | After (fix) |
|---|---|---|
| arch (layers) | pass | pass |
| clean: `DiskMount` | CC 18, cov 0.0%, CRAP 342.0 FAIL | CC 7, cov 87.5%, CRAP 7.1 pass |
| clean: new `diskMountFlags` / `diskPropagationFlags` | n/a | CC 3 / 3, cov 100% / 100%, pass |
| harden (changed lines 28-105) | not measurable: 0% covered | 21 mutants: 20 killed, 1 lived, 0 not covered = 95.2% pass |
| unit tests (`lxd/device`) | 0.8% statements | 1.2% statements; 3 new tests, real mounts in a private mount namespace |
| integration (`container_devices_disk`) | n/a | pass, incl. 3 new propagation subtests (24.8 s) |
| `make static-analysis` | n/a | NOT RUN: golangci-lint in `v1` fails to type-check untouched main too (Go 1.27.0 vs 1.27.2). gofmt, go vet, shellcheck clean |

The one LIVED mutant (`device_utils_disk.go:61`, remove `flags |= MS_BIND`) is a false report: applying it by hand turns both
unit tests red. gremlins errs towards under-reporting here.

## Where the framework earned its keep
- CRAP gate forced the refactor: no unit test can bring a complexity-18 function under 8, so `DiskMount` was split.
- Mutation gate found 3 real test gaps (no recursive test, no "writable without ro" test, flag map invisible to coverage).
- Independent fresh-context review (1 subagent, read-only) found a real defect: with `recursive=true` the non-`r` modes left
  submounts shared with the host (wider than asked). Fixed with a failing test first.
- Using it on real code found 5 defects in gauntlet itself, all fixed with tests: first-prefix layer matching (now longest),
  gremlins paths relative to its run dir (`[go] mutation_dir`), artifacts mixed with config (`--artifacts`), scope matching,
  and an `arch_check` that its own `clean` gate flagged (CC 9).
- Found a defect in my own test: Go subtests run on other OS threads, so the first passing run was not in the private mount
  namespace. The mutation run exposed it (timeouts and leaked mounts). Rewritten without `t.Run`.

## What the framework did not do (be honest)
- No `gauntlet loop`, `qa`, `report` or Workshop integration exist yet: SPEC (`spec.feature`, `qa.md`) was written by me and
  "approved" by the user's instruction, not by a per-run approval; gates were run by hand from a script.
- Go gates consume artifacts produced by other tools (gocyclo, `go test -coverprofile`, `go list`, gremlins), run in the `v1` VM.
- Complexity of Go is function-level only; CRAP uses statement coverage per function from `go tool cover -func`.

## Open concerns for upstream review (not addressed)
- Behaviour change: previously every non-empty `propagation` behaved as a recursive slave; now `private`, `shared`, `unbindable`
  etc. take effect. Needs a release note / API-extension discussion.
- Security: an admin who sets `shared`/`rshared` lets the container create mounts visible on the host under the source directory.
  That is what the key promises, but it deserves an explicit doc warning.
- Docs say `private` is the default; the real default is a recursive slave. `propagationTypes` in `disk.go` duplicates the new map.
- The shell subtest has no failure cleanup trap (same as its neighbours).
