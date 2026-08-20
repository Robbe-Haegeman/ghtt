# Giving each student unique content

Most of what a class receives is identical: the same start code, the same
assignment text. Sometimes it is not. Each student may need their own API key,
their own database password, their own dataset, or their own exam variant.

ghtt renders files **separately for every target repository**, so a value that
differs per student can be handed out without any student ever seeing another's.
The same mechanism corrects one file across a whole class without touching
anything else the students have changed.

## Where the per-student values come from

ghtt has no credential store and generates nothing. The only per-student data it
holds is that student's row from the student list, exposed to templates as
`record`. **Put the value in a column of `students.csv`:**

```csv
Username,Name,API key,DB password
ada,Ada Lovelace,key-ada-8f21,pw-ada-3311
bert,Bert Bertson,key-bert-77c9,pw-bert-4820
```

If the credentials have to be created somewhere first, generate them with your
own script, write them into the CSV, and let ghtt distribute them.

## Writing the template

A file ending in `.jinja` is rendered per repository and the result replaces it
without that suffix, whether it sits in the source repository or in a hand-out
directory. A `credentials.env.jinja`:

```jinja
API_KEY={{ students[0].record['API key'] }}
DB_PASSWORD={{ students[0].record['DB password'] }}
```

The keys of `record` are the CSV column headers, exactly as written.

`students` is the list of students of *this* repository. For individual
assignments it holds exactly one person, so `students[0]` is that student. For
group work it holds the whole group, so loop over it:

```jinja
{% for student in students %}
{{ student.username }}={{ student.record['API key'] }}
{% endfor %}
```

A group-wide value belongs in the group column instead, or in a lookup keyed on
`{{ group }}`.

See [configuration.md](configuration.md#template-files) for every variable a
template can use.

## Handing it out

**When you are creating the repositories anyway**, nothing extra is needed.
`create-repos` renders the same templates with the same variables, so the
credentials are in the first commit:

```shell
ghtt assignment create-repos
```

**When the repositories already exist**, put the files you want to hand out in
a directory of their own and pass it as `--content-dir`:

```
handouts/lab3-credentials/
└── credentials.env.jinja
```

```shell
ghtt assignment create-pr \
  --content-dir handouts/lab3-credentials \
  --branch credentials \
  --title "Your credentials" \
  --body "This branch adds your personal credentials. Merge it to continue."
```

For each selected repository ghtt clones **that repository's own default
branch**, writes the content directory into it, commits, pushes the result to
`--branch`, and opens a pull request. The pull request therefore contains
exactly the files you handed out and nothing else.

Check it first with `--dry-run`, which clones and reports which files each
repository would gain or have replaced, without committing or pushing anything.

### Paths are relative to the content directory

The content directory mirrors the layout of the student repository, so this:

```
handouts/lab3-fix/
├── credentials.env.jinja
└── docs/
    └── task.md
```

writes `credentials.env` and `docs/task.md`. That is also how you **correct a
file that already exists**: put the fixed version at the same relative path and
it replaces what is there. ghtt marks each file as it goes, so a replacement is
never silent:

```
Applying handouts/lab3-fix to course-ada
  + credentials.env
  ~ docs/task.md
```

`~` means the file already existed and was replaced; the pull request shows the
replacement as an ordinary diff, so the student can review it before merging.

A `.jinja` file is rendered for that student and loses the suffix. Any other
file is copied byte for byte, so images and archives survive intact.

### Why not just push the template repository

Without `--content-dir`, `create-pr` pushes the same branch from `--source` to
every repository, which is right for a class-wide update and wrong for a
hand-out: the branch is the template's state, so merging it carries every other
template file along and can conflict with work the student has already done.
`--content-dir` avoids that by branching from the student's repository instead.

It also means a hand-out needs **no access to the assignment template or its
history**. A colleague with the content directory, the student list, and a token
can run it.

## What happens when something is missing

A student whose row lacks the column fails on their own, by name, before
anything is pushed:

```
Error: Cannot render template for course-ada: 'dict object' has no attribute 'API key'
```

An empty credential is never handed out in place of a missing one. Fix the row
and rerun; repositories that already succeeded are not disturbed.

## Keeping the secrets out of the wrong places

**Keep the student list out of the source repository.** Everything in the
source directory is pushed to every student repository, and `students.csv` holds
every student's credentials. In the example project layout it sits next to
`ghtt.yaml`, one directory above `template/`, which is exactly right:

```
my-course/
├── ghtt.yaml
├── students.csv                     <- all credentials, never pushed
├── handouts/
│   └── lab3-credentials/            <- only these files are handed out
│       └── credentials.env.jinja
└── template/                        <- pushed by create-repos
```

The template itself is safe to commit: it contains placeholders, not values.

**A pushed credential is permanent.** It stays in that repository's Git history
even after the file is deleted, and everyone with access to the repository can
read it. That is fine for a credential that is scoped to one course and revoked
at the end of it. For anything longer-lived, hand out a short-lived token, or
use GitHub Actions secrets, which are set through the API rather than committed.

**Revoke at the end of the course.** `ghtt assignment remove-grant` removes
student access, but it does not invalidate a credential they already copied.
