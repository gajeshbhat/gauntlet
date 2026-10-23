# Benchmark results

| Cases | Checker | Caught | False alarms |
|---|---|---|---|
| gaming | baseline | 0/2 | - |
| gaming | coverage | 1/2 | - |
| gaming | gauntlet | 1/2 | - |
| planted | baseline | 0/3 | - |
| planted | coverage | 0/3 | - |
| planted | gauntlet | 0/3 | - |
| reference | baseline | - | 0/1 |
| reference | coverage | - | 0/1 |
| reference | gauntlet | - | 0/1 |
| weak-tests | baseline | 0/1 | - |
| weak-tests | coverage | 0/1 | - |
| weak-tests | gauntlet | 1/1 | - |
| all | baseline | 0/6 | 0/1 |
| all | coverage | 1/6 | 0/1 |
| all | gauntlet | 2/6 | 0/1 |

| Gate | Patches it rightly failed |
|---|---|
| harden | 1 |
