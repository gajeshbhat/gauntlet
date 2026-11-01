# Tutorial: your first run

Install gauntlet, run it, fix a failure, run again.

## 1. Install

Get `git`, `uv` and a sandbox (see the [README](../README.md#quickstart)), then:

```sh
uv tool install git+https://github.com/gajeshbhat/gauntlet
gauntlet --version
```

## 2. Initialise

```sh
cd your-project        # a git repository
gauntlet init .
```

This writes `gauntlet.toml`. If detection fails, create it with one line, such as `language = "python"`.

## 3. Run

```sh
gauntlet run . --report EVIDENCE.md
```

The first run is slow. A failing run prints:

```
src/app/parse.py:12: parse CRAP 17.8 > 8 (complexity 5, coverage 20%)
clean: 41 function(s) checked, 1 over CRAP 8
mutation score 84.0% < 90%
```

Exit `1` means a gate failed.

## 4. Fix the cause

- **CRAP too high**: test the function's branches, or split it.
- **Mutation score too low**: strengthen the assertions the survivors point at.

Don't add ignore comments; the `exclusions` gate counts them.

## 5. Run again

Repeat step 3. Exit `0` means every gate passed; attach `EVIDENCE.md` to your pull request.

Next: [how-to guides](how-to.md).
