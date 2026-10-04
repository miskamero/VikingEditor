# Contributing to VikingEditor

Thank you for your interest in contributing to VikingEditor!

VikingEditor is a desktop tool for editing Valheim character save files. Contributions of all kinds are welcome, including bug fixes, feature improvements, documentation, and bug reports.

## Reporting bugs

Before opening a bug report:

1. Make sure you are using the latest version of VikingEditor.
2. Check existing issues to see if the problem has already been reported.
3. Try to provide enough information for the issue to be reproduced.

When reporting a bug, include:

* VikingEditor version
* Operating system
* Valheim version, if relevant
* Steps to reproduce the problem
* What you expected to happen
* What actually happened
* Relevant error messages or logs
* Screenshots, if they help explain the problem

Please use the **Bug Report** issue template when possible.

## Suggesting features

Feature suggestions are welcome.

Before opening a feature request:

1. Check existing issues to see whether the feature has already been suggested.
2. Explain what you would like VikingEditor to do.
3. Explain why the feature would be useful.
4. Include examples or implementation ideas if you have them.

Please use the **Feature Request** issue template.

## Pull requests

Please use the [pull request template](.github/pull_request_template.md) when submitting a pull request.

Pull requests should generally:

* Address a specific bug, feature, or improvement.
* Keep changes focused and reasonably small.
* Include a clear description of what was changed.
* Be tested before submission.
* Avoid unrelated changes.
* Avoid committing generated files, personal configuration, secrets, or other unnecessary files.
* Update relevant documentation when necessary.

Before submitting a pull request, make sure the project still starts and that your changes work as expected.

### Automated tests

The [Unit tests workflow](.github/workflows/unittests.yml) runs the suite on every push and pull request using Windows and Python 3.11. It can also be started manually from GitHub's Actions tab. Dependency downloads are cached using `requirements.txt`. A failing test fails the workflow; inspect the **Run unittest suite** step for details.

The suite uses Python's built-in `unittest` and the project's existing dependencies. From the repository root, after installing `requirements.txt`, run:

```sh
python -m unittest discover -s tests -t . -v
```

Or run a single module or test when working on a specific area:

```sh
python -m unittest tests.test_validation -v
python -m unittest tests.test_editor.InventoryTests.test_cancel_clear_preserves_inventory -v
```

The tests cover item validation, binary encoding, player-data and `.fch` round trips, save checksums, and editor behavior across all eight tabs. Qt widgets run offscreen; message boxes are mocked, save files use temporary directories, and the parser and item selector use a small fixture database. No Valheim installation, personal saves, or cached item database is needed. Temporary files are removed automatically.

Add regression tests under `tests/test_*.py`. Use `subTest` for boundary cases, `TemporaryDirectory` for file operations, and the shared Qt test setup for widgets. These tests check application behavior, not screenshot appearance, the packaged
executable, or compatibility with a running game. Continue to review UI changes visually and verify save compatibility separately when changing the file format.

### Commit messages

Please use clear and descriptive commit messages.

For example:

```text
Fix missing beard styles
```

or:

```text
Add Linux Steam path detection
```

Avoid vague messages such as:

```text
stuff
```

or:

```text
nöfnöf
```

If a commit addresses an existing issue, including the issue number can be useful:

```text
Fix missing beard styles (#5)
```

## AI-assisted contributions

AI-assisted development is allowed and welcome.

Tools such as GitHub Copilot, Claude, ChatGPT, and other AI development tools may be used to assist with coding, debugging, documentation, and other development tasks.

However, contributors are responsible for the changes they submit. AI-generated or AI-assisted code should be reviewed, understood, and tested by the contributor before being submitted.

Please do not add AI tools or AI services as commit authors or co-authors unless explicitly requested by the project maintainer.

The human contributor responsible for the work should remain the author of the commit.

In particular, please avoid automatically generated commit trailers such as:

```text
Co-Authored-By: Claude ...
```

unless the project maintainer has explicitly requested such attribution.

## Code quality

VikingEditor is primarily a Python desktop application.

When modifying the code:

* Follow the existing project structure and conventions.
* Prefer simple and readable solutions.
* Avoid unnecessary changes outside the scope of the contribution.
* Do not introduce dependencies without a good reason.
* Test changes that affect character saves carefully.

Because VikingEditor works with user save files, changes involving save-file reading or writing should receive particular attention and should avoid risking data loss.

## Pull request review

Pull requests may be reviewed before being merged.

Reviewers may request:

* Changes to the implementation
* Additional testing
* Documentation updates
* Simplification of the code
* Changes to the commit history

Please address review comments or explain why a suggested change should not be made.

## License

By contributing to VikingEditor, you agree that your contributions may be distributed under the project's existing [license](LICENSE).

Thank you for helping improve VikingEditor!
