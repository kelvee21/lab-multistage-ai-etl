# adaptability

the brief scores this at 20%: minimal dependency on specific tools and models.
so what actually happens if i swap the tools.

## the rule i designed around

nothing that matters lives inside a tool.

- `outputs/extraction_contract.json` is plain json
- `etl/` is plain python
- the run evidence is markdown and logs

anything that can read and write those files can take over any stage. there is
no api call between the stages, no model in the middle, no proprietary format.

## swapping each stage

| stage | what i used | what else works | what changes |
|---|---|---|---|
| 1 | a chat ai in the browser | any chat ai | nothing. paste the same prompt and the same samples, you get the same deliverable shape, json plus open questions |
| 2 | vs code with the assistant | any ide assistant, or the same chat ai | keep the contract as authority and review the diff the same way |
| 3 | terminal agent and powershell | any terminal | the commands in `prompts/STAGE-3-*.md` are plain `pytest` and `python -m etl run`. only the reporting part changes |

the prompts name brands only because the brief asks for them by name. nothing
in the code needs one.

## why the runtime part is vendor free

the pipeline never calls a model. `etl/` is stdlib plus openpyxl. i wanted this
for a practical reason, not only a scoring reason: the numbers in the warehouse
should not depend on which model wrote the code. if the extraction is
deterministic, running it in six months gives the same answer, and i can prove
it by running it twice.

the tests prove the same thing. they need no network and no key.

## what does depend on the files, honestly

two things, and i would rather name them than hide them.

- **sheet name patterns and the letter-O rule are contract entries.** a source
  that renames its tabs needs a one line contract change. that is the point of
  the design, a reviewable line instead of a code edit.
- **`branch_aliases` and `ignore_columns` came from sweeping these six files.**
  next month a new branch name shows up. it does not get mangled, it lands in
  `unmapped_column` quarantine where i will see it.

## adding data

| what changed | what i touch |
|---|---|
| same month, new files | drop them in `data/raw`, add a source entry |
| same files, new name | edit the `file` field |
| a genuinely new layout | add a source with its own `columns` map |
| a new branch | add it to `branch_headers` |

the readers key off the contract, so none of these are code changes. the
exception is a layout shape with no equivalent in the two grids i already
handle, and then i add a reader and say so here.
