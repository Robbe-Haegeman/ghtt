# Giving each student unique content

Most of what a class receives is identical: the same start code, the same
assignment text. Sometimes it is not. Each student may need their own API key,
their own database password, their own dataset, or their own exam variant.

ghtt renders the source repository **separately for every target repository**,
so a value that differs per student can be handed out without any student ever
seeing another's.

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

Any file in the source repository ending in `.jinja` is rendered per repository
and the result replaces it without that suffix. A `credentials.env.jinja`:

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

**When the repositories already exist**, use the per-repository mode of
`create-pr`. It renders the source once per target, pushes the result to a
branch in that student's repository, and opens a pull request:

```shell
ghtt assignment create-pr --per-repository \
  --branch credentials \
  --title "Your credentials" \
  --body "This branch adds your personal credentials. Merge it to continue."
```

Check the plan first with `--dry-run`, which shows the targets without pushing
anything.

Without `--per-repository`, `create-pr` pushes the *same* branch to every
repository, which is the right mode for a class-wide correction and the wrong
one here: it would hand every student the same rendering.

`--per-repository` cannot be combined with `--branch-already-pushed`, because
there is no single branch to have pushed in advance.

## Rotating a value

Each run renders and commits fresh on top of the source's default branch, so a
second hand-out with different content has a history that has diverged from the
first. The push is refused, and ghtt tells you so:

```
Warning: could not push to course-ada: ...
If the branch already exists with different history, rerun with --force-push to
overwrite it.
```

Rerun with `--force-push` to replace the branch. The pull request that is
already open picks up the new commit; ghtt does not open a second one.

```shell
ghtt assignment create-pr --per-repository --force-push \
  --branch credentials --title "Your credentials" --body "Updated credentials."
```

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
├── students.csv        <- all credentials, never pushed
└── template/           <- pushed to every student repository
    └── credentials.env.jinja
```

The template itself is safe to commit: it contains placeholders, not values.

**A pushed credential is permanent.** It stays in that repository's Git history
even after the file is deleted, and everyone with access to the repository can
read it. That is fine for a credential that is scoped to one course and revoked
at the end of it. For anything longer-lived, hand out a short-lived token, or
use GitHub Actions secrets, which are set through the API rather than committed.

**Revoke at the end of the course.** `ghtt assignment remove-grant` removes
student access, but it does not invalidate a credential they already copied.
