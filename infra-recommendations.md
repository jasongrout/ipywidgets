# Infrastructure update recommendations

Status of the repo's build/test/packaging infrastructure as of August 2026,
following the migration to the standalone `jupyter-builder` toolchain and the
drop of JupyterLab 3 support. Items are ordered by priority within each
section.

## Already done on this branch

For context, these landed on `claude/dev-install-jupyterlab-compat-56my6v`:

- `jupyterlab_widgets` builds with the standalone `jupyter_builder` package
  (`@jupyter/builder` on npm, Rspack-based) instead of the deprecated
  `@jupyterlab/builder` / `jupyter labextension build`. The pyproject build
  requirement is now `jupyter_builder>=1.0` instead of `jupyterlab~=4.0`, so
  wheel/sdist builds no longer need JupyterLab in the build environment.
- `dev-install.sh` works again (the old dual builder range broke
  `jupyter labextension build` on JupyterLab >= 4.6) and no longer installs
  `jupyter_packaging`.
- JupyterLab 3 support is dropped: dependency ranges are narrowed to the
  Lab 4 generation (`@jupyterlab/* ^4`, `@jupyterlab/services ^7`,
  `@lumino/* ^2`, `@jupyterlab/rendermime-interfaces ^3.8.0`).
- A snapshot-free labextension smoke test (`ui-tests/tests/plugin.test.ts`)
  asserts the manager plugin registers and activates; verified against
  JupyterLab 4.0.13 and 4.6.2.
- `@jupyterlab/galata` updated to `^5.6.2` (with `@playwright/test ^1.60.0`):
  the previously locked 5.4.1 page fixture hangs against JupyterLab >= 4.6.
- A CI patch (not pushable from the automated session, which lacks the
  `workflow` scope) swaps `jupyter-packaging` for `jupyter_builder` in the
  workflows, removes the `jupyterlab==4.5.8` pin, and adds a
  `labextension-compat` matrix job testing `jupyterlab==4.0.*` and latest.

## High priority: real breakage or stale debt

### 1. Migrate `widgetsnbextension` off `jupyter_packaging`

`python/widgetsnbextension` still uses the deprecated, unmaintained
`jupyter_packaging` as its build backend (`setup.py` imports it;
`pyproject.toml` has `requires = ["jupyter_packaging~=0.10,<2"]`). Migrate it
to hatchling + `hatch-jupyter-builder`, mirroring `jupyterlab_widgets`. That
allows removing `jupyter-packaging` from `docs/requirements.txt` and from the
release environment in `docs/source/dev_release.md`.

### 2. Remove or fix the dead git hooks

Root `package.json` carries husky v4-style config (`"husky": {"hooks": ...}`)
but husky 7 is installed, which requires a `.husky/` directory (absent) and a
`prepare` script (absent). The `lint-staged` pre-commit hook and the
`yarn integrity` pre-push hook have therefore not been running for anyone.
Either wire husky up properly, or delete husky + lint-staged and rely on the
CI lint job, which is what has actually been guarding the repo.

### 3. Raise and align the Python floor

All three Python packages declare `python_requires >= 3.7` while classifiers
and CI say 3.9–3.13, and Python 3.9 has been EOL since October 2025.
Recommendation: set `requires-python >= 3.10` everywhere, drop 3.9 from the
CI matrix, and add 3.14 (released October 2025, currently untested).

### 4. Bump CI action versions

`actions/cache@v3` and `actions/setup-python@v4` are a generation behind
(current: v4 and v5). Fold into the same workflow patch already pending.

### 5. Fix the `engines` declaration

Root `package.json` declares `"node": ">=14"`. Node 14 is long EOL and the
current toolchain does not run on it. Bump to `>=18` (or `>=20`) so the
declaration matches reality.

## Medium priority: coordinated upgrades, each deserving its own PR

### 6. TypeScript 5 toolchain

The root `resolutions` pins TypeScript to `~4.9.4`, with typedoc `~0.23` and
typescript-eslint 5 chained to it. The JupyterLab 4 ecosystem is TS 5.x;
everything compiles today, but with dependency ranges now resolving current
Lab packages, newer typings will eventually break under a TS 4.9 compiler.
One coordinated upgrade: TypeScript 5 → typedoc 0.26+ → typescript-eslint 8
(optionally ESLint 9 flat config in the same pass).

### 7. Lerna 5

Works on Node 22 today but is two majors behind and is used mostly as a task
runner. Either bump to lerna 8+, or drop it in favor of
`yarn workspaces foreach`, which the yarn 3 setup already provides.

### 8. PEP 621 packaging for `ipywidgets` and `widgetsnbextension`

Both still use `setup.py` + `setup.cfg`. Migrating to PEP 621
`pyproject.toml` (hatchling) matches `jupyterlab_widgets` and pairs naturally
with item 1.

## Lower priority / verify first

- **Classic notebook test leg**: `devinstall.yml` installs `notebook~=6.0` on
  Python 3.13 to exercise the classic-notebook path. Verify that job still
  passes; if classic Notebook 6 support is being retired in favor of
  Notebook 7 (which loads the labextension), this leg could simplify to
  nbclassic or be removed.
- **Docs stack**: `recommonmark` is deprecated; `myst-nb <0.18` and the
  jupyterlite pins are old; the README compatibility table's JupyterLab
  column is empty; `docs/source/dev_install.md` still describes the old
  yarn/notebook-main workflow.
- **Small inconsistencies**: `ui-tests`' `test:report` script uses
  `http-server`, which is not in its devDependencies; the root devDependency
  `@jupyterlab/buildutils "^3.5.2 || ^4.0.0"` should narrow to `^4.0.0` for
  consistency with the Lab-4-only decision.
