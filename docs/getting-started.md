# Getting Started

A practical first guide for people who want to **run AutoDev locally, understand what it does, and get a successful first run quickly**.

If you only need setup details, see `docs/onboarding.md`.
If you want the laptop-friendly GUI path, see `docs/LOCAL_SIMPLE_MODE.md`.

## What AutoDev is for

AutoDev takes a Markdown PRD and runs a repeatable workflow:

1. parse the PRD,
2. make an implementation plan,
3. generate/update project files,
4. run validators locally,
5. retry targeted fixes when checks fail,
6. save artifacts so you can inspect what happened.

Use it when you want more than “generate some code” — you want a **traceable PRD-to-code run** with evidence under `.autodev/`.

## What you should expect

AutoDev does **not** replace review or product thinking.
It is best for:
- trying a PRD quickly,
- generating a first working baseline,
- validating changes with local tools,
- iterating with visible artifacts and bounded retries.

## Fastest first run

From the repo root:

```bash
make demo-bootstrap
```

That path is the easiest way to confirm the repo is set up correctly.

If you want the GUI to stay open after setup checks:

```bash
make demo-bootstrap-serve
```

## Minimal manual setup

If you prefer to start by hand:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
autodev --help
```

Then configure an OpenAI-compatible backend in `config.yaml`.
For full provider examples, use `docs/onboarding.md`.

## Your first real run

Use the sample PRD first:

```bash
autodev --prd examples/PRD.md --out ./generated_runs --profile enterprise
```

What happens next:
- a timestamped run directory is created under `generated_runs/`
- generated files are written there
- AutoDev stores execution artifacts under `<run_dir>/.autodev/`
- the final summary is written to `<run_dir>/.autodev/REPORT.md`

## What to look at after a run

Open these first:
- `<run_dir>/.autodev/REPORT.md`
- `<run_dir>/.autodev/prd_struct.json`
- `<run_dir>/.autodev/plan.json`
- any `task_*_last_validation.json` files

These tell you:
- how the PRD was normalized,
- what tasks were planned,
- which validators passed or failed,
- whether AutoDev needed fix loops.

## Recommended beginner workflow

After the sample PRD works:

1. Copy `examples/PRD.md` and replace it with a very small PRD.
2. Keep scope tight: one feature, a few acceptance criteria, no big integrations.
3. Run AutoDev again.
4. Inspect `.autodev/REPORT.md` before changing prompts or config.
5. Only move to a larger PRD after a small run is stable.

A good first PRD usually asks for:
- one API endpoint, or
- one small CLI workflow, or
- one focused CRUD-style feature.

## When to use local-simple mode

Use local-simple when you want a lightweight operator flow instead of raw CLI commands:

```bash
autodev local-simple --runs-root ./generated_runs --open
```

This is useful when you want:
- one-click Quick Run,
- recent run visibility,
- artifact viewing,
- retry/stop controls from the GUI.

See `docs/LOCAL_SIMPLE_MODE.md` for the full flow.

## Common beginner mistakes

- Starting with a huge PRD instead of a tiny one
- Forgetting to configure a reachable model endpoint
- Expecting AutoDev to write directly into this repo instead of the run output directory
- Reading only console output and ignoring `.autodev/REPORT.md`
- Using a heavy validation profile before the basic flow works

## Good next steps

After your first successful run, try one of these:
- run with `--interactive` to add a manual approval step,
- try `--resume` on a partial run,
- compare `local_simple` vs `enterprise` profiles,
- move from `examples/PRD.md` to your own small PRD,
- explore autonomous mode after the basic CLI flow feels familiar.

For deeper setup and operator docs:
- `docs/onboarding.md`
- `docs/LOCAL_SIMPLE_MODE.md`
- `docs/AUTONOMOUS_MODE.md`
