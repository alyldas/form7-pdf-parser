# Release process

Release Please runs after every push to `main`. It reads the Conventional Commit history and
creates or updates a release pull request with the next version and changelog entries.

## Pull request titles

The repository is squash-only and uses the pull request title for the squash commit. Use:

```text
type(scope?): lowercase summary
```

Examples:

```text
fix: preserve page order after annotation
feat(cli): add a validation-only command
docs: clarify synthetic fixture requirements
chore(deps): update development dependencies
```

- `fix:` or `docs:` creates a patch release.
- `feat:` creates a minor release.
- `type!:` or a `BREAKING CHANGE:` footer creates a major release.
- `chore:`, `test:`, and `refactor:` normally create no release.

The required title and package checks run for every pull request. Release Please uses the
`RELEASE_PLEASE_TOKEN` repository secret so its release pull requests trigger the same checks.
Use a fine-grained token limited to this repository with read/write access to contents and pull
requests. Issue write access is also needed for release lifecycle labels.

## Publishing

Merge the release pull request when the accumulated changes should be published. Release Please
creates the GitHub release and tag, then the same workflow builds, verifies, and attaches the
wheel and source distribution.

If asset creation or upload fails after the GitHub release exists, re-run the failed workflow
jobs. The workflow finds the release tag on the original commit and safely replaces any partial
assets. To rebuild assets for a specific release, run the Release Please workflow manually and
provide its existing tag in the `release_tag` input.

## Recovery

If a pull request was squash-merged with an incorrect title, edit the merged pull request body
and add:

```text
BEGIN_COMMIT_OVERRIDE
fix: describe the releasable change
END_COMMIT_OVERRIDE
```

Re-run the Release Please workflow. Commit overrides are a recovery mechanism; new pull requests
should use a valid title before merge.
