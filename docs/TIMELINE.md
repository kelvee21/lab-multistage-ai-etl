# my week

two labs at the same time. this one is the foundation module (dataops etl), the
tmdb movie analysis one is the specialisation. they are in separate repos, same
git identity, same week.

tmdb was due sat 17th 8pm, so that one got frozen first and this one kept going
over the weekend.

## mon 12

brood. read the brief, made the folder, gitignore, requirements, run.ps1.
nothing clever, just somewhere to put things.

went through the raw folder. 6 workbooks are usable. the 5 zips are desktop
backups up to 2gb, skipping those. the rest is slides and finance packs, out of
scope.

openpyxl only to start. wrote tools/inspect_workbook.py because i wanted to see
the tabs without opening excel. stdlib zipfile, so it runs anywhere.

tmdb: scaffolded it, then fixed the fetch script.

## tue 13

brood. dumped the production and dispatch tabs, pasted a few samples into a chat
ai and asked for a contract. first prompt was too vague and it mapped columns off
one screenshot and zeroed the blanks. rewrote the prompt with role, goal,
context, format and the actual facts about the files.

got v1.0.0. 4 day sources, 12 branch columns, and i believed that was all of
them.

## wed 14

brood. v1.0.0 was wrong. i had looked at the first few tabs, then i looped over
every tab in all four june files. VISTA and C SHOP were there the whole time.
that is 2 more branches on every row of a month, so it mattered.

v1.0.1: 14 branches, ignore_columns with a reason next to each one, the TOTAL
row rule, and the row total column. GDYEAR on the waste 14th tab became an
alias, because it sits exactly where G YEAR sits everywhere else.

then added the two weekly sales files as transactions sources. v1.1.0, which is
what stage 2 reads.

started the code. contract.py fails fast on a bad rule, normalize.py does the
text, number and date cleaning.

tmdb: cleaned the table.

## thu 15

brood. the day tab reader, which is the hard one. it has to find the header row
because the dispatch 22nd tab has a number sitting above it, treat column A as
the row number, map the branch headers, use the aliases, skip the derived
columns and never turn a blank into a 0.

sales reader after that. both weekly files start with a blank row so the header
is really row 2.

validate.py last, because until both readers existed there was nothing to gate.

tmdb: profit and roi.

## fri 16

brood. load.py, the sqlite star schema and the csv exports. primary key on
(date, product, branch) so a duplicate insert blows up instead of quietly
doubling a number. __main__.py for the cli.

tests last on purpose. 26 of them, all building their own fake workbooks so they
run with no bakery data and no network.

tmdb: charts, then the notebook.

## sat 17

brood. docs. diagram, plan, the brief mapped line by line, adaptability.

tmdb: report, then tidy up. frozen at 8pm and submitted.

## sun 18

brood. finished the stage prompts so the iteration is in the repo.

then ran it on the real files for the first time end to end. 26 green, pipeline
runs, and the report had things in it i did not expect.

wrote three checks from scratch with no etl imports. first attempt compared
against the wrong total column and gave me 551 false alarms, which told me the
contract needed to pin the column choice more tightly than it did.

found and fixed one wrong claim of my own in the contract, the note saying the
20th to 25th production tabs were empty. they are not, each has one row in it.

readme last, then walked the brief line by line against the rubric.
