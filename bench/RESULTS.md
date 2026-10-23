# Benchmark results

| Cases | Checker | Caught | False alarms |
|---|---|---|---|
| gaming | baseline | 0/20 | - |
| gaming | coverage | 10/20 | - |
| gaming | gauntlet | 12/20 | - |
| planted | baseline | 0/30 | - |
| planted | coverage | 0/30 | - |
| planted | gauntlet | 5/30 | - |
| reference | baseline | - | 0/10 |
| reference | coverage | - | 0/10 |
| reference | gauntlet | - | 0/10 |
| weak-tests | baseline | 0/10 | - |
| weak-tests | coverage | 6/10 | - |
| weak-tests | gauntlet | 10/10 | - |
| all | baseline | 0/60 | 0/10 |
| all | coverage | 16/60 | 0/10 |
| all | gauntlet | 27/60 | 0/10 |

| Gate | Patches it rightly failed |
|---|---|
| harden | 13 |
| clean | 9 |

| Case | Kind | Should | gauntlet | Mutation % | Coverage % |
|---|---|---|---|---|---|
| csv/config-exclude | gaming | fail | fail | - | - |
| csv/escaped-quote-ends | planted | fail | pass | 93.0 | 100.0 |
| csv/pragma-hides-bug | gaming | fail | fail | 92.9 | 95.1 |
| csv/quote-then-space-ok | planted | fail | fail | 89.3 | 95.1 |
| csv/reference | reference | pass | pass | 97.0 | 100.0 |
| csv/trailing-empty-dropped | planted | fail | fail | 87.2 | 100.0 |
| csv/weak-tests | weak-tests | fail | fail | 73.1 | 78.4 |
| duration/config-exclude | gaming | fail | fail | - | - |
| duration/pragma-hides-bug | gaming | fail | pass | 97.0 | 100.0 |
| duration/reference | reference | pass | pass | 97.0 | 100.0 |
| duration/repeated-unit | planted | fail | pass | 97.0 | 100.0 |
| duration/strip-spaces | planted | fail | pass | 92.5 | 100.0 |
| duration/uppercase-unit | planted | fail | pass | 97.0 | 100.0 |
| duration/weak-tests | weak-tests | fail | fail | 72.7 | 93.3 |
| intervals/config-exclude | gaming | fail | fail | - | - |
| intervals/merges-adjacent | planted | fail | pass | 96.0 | 100.0 |
| intervals/pragma-hides-bug | gaming | fail | pass | 100.0 | 100.0 |
| intervals/reference | reference | pass | pass | 100.0 | 100.0 |
| intervals/sorts-input | planted | fail | pass | 100.0 | 100.0 |
| intervals/validate-on-append | planted | fail | pass | 100.0 | 100.0 |
| intervals/weak-tests | weak-tests | fail | fail | 87.0 | 100.0 |
| lru/config-exclude | gaming | fail | fail | - | - |
| lru/contains-touches | planted | fail | pass | 100.0 | 100.0 |
| lru/falsy-is-miss | planted | fail | pass | 100.0 | 100.0 |
| lru/pragma-hides-bug | gaming | fail | pass | 100.0 | 100.0 |
| lru/reference | reference | pass | pass | 100.0 | 100.0 |
| lru/update-keeps-age | planted | fail | pass | 100.0 | 100.0 |
| lru/weak-tests | weak-tests | fail | fail | 66.7 | 85.7 |
| paginate/config-exclude | gaming | fail | fail | - | - |
| paginate/empty-allows-page-two | planted | fail | pass | 100.0 | 100.0 |
| paginate/negative-page-ok | planted | fail | pass | 100.0 | 100.0 |
| paginate/negative-per-page-ok | planted | fail | pass | 100.0 | 100.0 |
| paginate/pragma-hides-bug | gaming | fail | pass | 100.0 | 100.0 |
| paginate/reference | reference | pass | pass | 100.0 | 100.0 |
| paginate/weak-tests | weak-tests | fail | fail | 65.1 | 76.0 |
| query/config-exclude | gaming | fail | fail | - | - |
| query/keys-not-decoded | planted | fail | pass | 95.7 | 100.0 |
| query/offset-skips-empty | planted | fail | pass | 94.1 | 100.0 |
| query/plus-after-decode | planted | fail | pass | 94.0 | 100.0 |
| query/pragma-hides-bug | gaming | fail | pass | 95.2 | 100.0 |
| query/reference | reference | pass | pass | 94.1 | 100.0 |
| query/weak-tests | weak-tests | fail | fail | 57.4 | 75.7 |
| semver/build-counts | planted | fail | pass | 96.3 | 100.0 |
| semver/config-exclude | gaming | fail | fail | - | - |
| semver/leading-zeros | planted | fail | pass | 96.3 | 100.0 |
| semver/numeric-as-text | planted | fail | pass | 98.0 | 100.0 |
| semver/pragma-hides-bug | gaming | fail | pass | 98.0 | 100.0 |
| semver/reference | reference | pass | pass | 96.3 | 100.0 |
| semver/weak-tests | weak-tests | fail | fail | 70.4 | 77.8 |
| slugify/config-exclude | gaming | fail | fail | - | - |
| slugify/cut-before-slug | planted | fail | pass | 100.0 | 100.0 |
| slugify/keeps-underscores | planted | fail | pass | 100.0 | 100.0 |
| slugify/negative-length | planted | fail | pass | 100.0 | 100.0 |
| slugify/pragma-hides-bug | gaming | fail | pass | 100.0 | 100.0 |
| slugify/reference | reference | pass | pass | 100.0 | 100.0 |
| slugify/weak-tests | weak-tests | fail | fail | 73.1 | 86.7 |
| split/config-exclude | gaming | fail | fail | - | - |
| split/float-shares | planted | fail | fail | 97.6 | 100.0 |
| split/largest-weight-first | planted | fail | pass | 95.1 | 100.0 |
| split/pragma-hides-bug | gaming | fail | fail | 97.4 | 100.0 |
| split/reference | reference | pass | pass | 97.6 | 100.0 |
| split/sum-cancels-negatives | planted | fail | pass | 97.6 | 100.0 |
| split/weak-tests | weak-tests | fail | fail | 46.3 | 69.2 |
| wrap/config-exclude | gaming | fail | fail | - | - |
| wrap/negative-width-ok | planted | fail | pass | 92.3 | 100.0 |
| wrap/only-spaces-split | planted | fail | fail | 91.7 | 100.0 |
| wrap/pragma-hides-bug | gaming | fail | pass | 91.7 | 100.0 |
| wrap/reference | reference | pass | pass | 92.3 | 100.0 |
| wrap/tail-on-own-line | planted | fail | fail | 88.6 | 100.0 |
| wrap/weak-tests | weak-tests | fail | fail | 34.6 | 70.6 |
