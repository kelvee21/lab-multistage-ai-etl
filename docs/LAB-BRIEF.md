# the brief, line by line

every line of the lab brief and where i answer it. weights are from the brief.

## scenario

> create a workflow that solves a problem by chaining outputs between at least
> two different ai ux types

chat -> ide -> cli. three stages, more than the two asked for. the file stage 1
writes is read by stage 2, and the package stage 2 writes is what stage 3 runs.
see `README.md` and `docs/diagram.md`.

## learning objectives

| objective | how i did it |
|---|---|
| design workflows across different ux types | 3 stages, `docs/diagram.md` |
| integrate output from one tool into another | the contract json is handed from the chat session straight into the ide session, `prompts/` |
| tool agnostic, adaptable to other providers | `docs/adaptability.md`, and no model is called at runtime |

## required tools

| brief needs | what i used |
|---|---|
| a chat based ai | a chat ai in the browser, prompt in `prompts/STAGE-1-chat-profile-and-contract.md` |
| an ide with ai | vs code with the assistant, prompt in `prompts/STAGE-2-ide-build-etl.md` |
| a cli based ai | terminal agent and plain powershell, prompt in `prompts/STAGE-3-cli-run-and-verify.md` |
| test data | 6 real B BROOD bakery workbooks in `data/raw/`, kept local, plus fake workbooks the tests build themselves |

## instructions

| step | where |
|---|---|
| 1. pick a problem that splits into stages | the hand typed one tab per day bakery workbooks. `docs/PLAN.md` section 1 |
| 2. choose two tools from different ux categories | chat, ide and cli. three, so the minimum is met |
| 3. one tool's output is the next tool's input | `outputs/` to `etl/` to `runs/`. the chain in `README.md` |
| 4. implement and test end to end | `python -m etl run`, `pytest` 26 green. `runs/RUN-LOG.md` |
| 5. document with a diagram and step by step notes | `docs/diagram.md`, `README.md`, `docs/PLAN.md`, `prompts/` |

## deliverables

| deliverable | file |
|---|---|
| working workflow across 2 ux types | the chain above, runnable with `.\run.ps1` |
| workflow diagram | `docs/diagram.md`, mermaid and ascii |
| written documentation | this file, `README.md`, `docs/PLAN.md`, `docs/adaptability.md`, `runs/RUN-LOG.md` |

## criteria

| criteria | weight | what i did | proof |
|---|---|---|---|
| functionality | 40% | runs end to end on the real files, 26 tests green, running twice gives the same counts | `runs/RUN-LOG.md` |
| adaptability | 20% | prompts and contract name no vendor, and the pipeline calls no model at run time so it works offline | `docs/adaptability.md`, tests run with no network |
| documentation | 20% | mermaid + ascii diagram, the stage by stage chain, and a list of what is still unknown | `docs/diagram.md`, `README.md` |
| efficiency | 20% | 91 day tabs plus 2 weekly sales files become 20684 warehouse rows in about 14 seconds, rebuilt from scratch every run | `runs/RUN-LOG.md` timings |

## deviations and things to know

- the real workbooks are not in the repo. `data/raw/` is gitignored because they
  are a client's business data. a reviewer without them can still run `pytest`,
  read the contract and read the run log.
- `etl/` is at the repo root instead of under `src/` so `python -m etl run` needs
  no `PYTHONPATH`. `docs/PLAN.md` section 9.
- stage 2 and stage 3 are the same ux type split in two (an ide assistant and a
  terminal agent), so the chain has three distinct stages either way.
- three checks in `runs/RUN-LOG.md` were written a second time from scratch with
  no `etl` imports on purpose, so they are not the pipeline agreeing with
  itself.
