# Contributing

Thanks for considering a contribution. This document covers the **legal
requirement** (DCO sign-off) and the general expectations for contributing to Max.

---

## 1. Sign your commits (required)

This project uses the **Developer Certificate of Origin** instead of a CLA. It is the
lightweight way of stating that you have the right to submit the code under this
project's license. There is no separate document to sign — you add one line to your
commit.

```bash
git commit -s -m "fix: ..."
```

`-s` appends:

```
Signed-off-by: Your Name <you@example.com>
```

The name and email must be real (a pseudonym is fine, but it has to be a reachable
identity). Full text: [`DCO`](DCO).

If you forgot to sign off, amend the last commit:

```bash
git commit --amend -s --no-edit && git push --force-with-lease
```

For several commits at once: `git rebase --signoff main`

---

## 2. Code and commit conventions

Contributions to Max should be appropriate to the project and should work as intended.

**Code:** Match the surrounding file — its comment density, naming and idioms. Comments
should explain *why*, not restate what the code does.

**Commits:** Keep commits focused and give them a clear, descriptive subject. DCO sign-off
is required as described above.

The maintainer is free to experiment, break things, and commit work that is incomplete,
rough, or temporarily non-functional while developing Max. **That latitude applies to the
maintainer's own work only.** Contributors are expected to submit work that is appropriate
to the project and works as intended.

## 3. Contributing to Max

Contributions should be made to Max itself. Max is an independent downstream project and
does not send pull requests back to Calivi.

Before submitting a change, make sure it is relevant to Max, does not introduce avoidable
regressions, and has been checked appropriately for the change being made.

---

## 4. Security

If you find a vulnerability, **do not open a public issue** — report it privately as
described in [SECURITY.md](SECURITY.md).

Things to know while contributing:

- Web search results and document attachments count as **untrusted content** and are
  passed to the model inside delimited blocks (`_wrap_untrusted`). If you add another
  path that carries external content to the model, use the same wrapping.
- Tools that change state run **only after a person approves each call**: `registry.execute`
  refuses a `mutating=True` tool unless the approval flow in `routers/chats.py` returned a yes,
  and MCP tools without `readOnlyHint` stay off until an admin opts in. Contributions must not
  bypass this approval boundary.
- The frontend is served under a strict Content-Security-Policy. If you edit the inline
  theme-bootstrap script in `index.html`, **recompute the CSP hash** (explained in a
  comment in `frontend/nginx.conf`), or the theme will flash on load.
