# GitHub release instructions — Adrian

The public target already exists. Adrian authorized PR #3 on `adrian/core-api-ai` and its merge into main, then explicitly authorized the current tested follow-up directly on main. Preserve the original authored commits and use normal pushes; do not force-push or bypass protection. The commands below describe the normal feature-branch workflow for future work and team setup. Collaborator invitations, protection settings and deployment remain separate. See GitHub Actions for remote CI status.

Designated target from Adrian: https://github.com/adrian-hue-pixel/TrendTrace. The uploaded archive originated from TrendTrace; the release zip intentionally omits its .git history. Preserve the target clone's own .git folder. If teammates have changed the target since this archive, review and reconcile their changes before copying over files.

## Repository and branch

If the public target already exists (it did at our earlier check):

```bash
git clone https://github.com/adrian-hue-pixel/TrendTrace.git
cd TrendTrace
git status
git switch main
git pull --ff-only
git switch -c adrian/core-api-ai
```

If you already have its local clone, use that clean clone and omit git clone/cd. If the branch name already exists, use git switch adrian/core-api-ai and inspect its state instead of recreating it. Do not reset or discard teammates' local work.

Only if the target repository has not been created, first use GitHub's **New repository**, set owner adrian-hue-pixel/name TrendTrace, select **Public**, initialise main, then follow the clone commands above. Alternatively with authenticated GitHub CLI:

```bash
gh repo create adrian-hue-pixel/TrendTrace --public --add-readme --clone
cd TrendTrace
git switch -c adrian/core-api-ai
```

Copy the **contents** of the release zip's TRENDTRACE folder into that target clone. Include dotfiles such as .env.example and .gitignore. Keep the clone's .git, never copy a virtual environment, local .env, raw NASA downloads or generated reports. The zip includes Karnish's existing backend plus Adrian's additions; when main only contains a README, the PR will naturally include that baseline too.

## Verify, commit and open the PR

Create a Python 3.11 venv, activate it and install the README dependencies first. Run from the target clone:

```bash
python -m pytest
python scripts/security_audit.py
git diff --check
git status --short
git diff --stat
git diff
git add README.md .env.example .gitignore .python-version requirements.txt requirements-dev.txt pytest.ini backend docs scripts data/mock data/processed/.gitkeep
git diff --cached --stat
git diff --cached
```

Review the staged content. Add any other intended baseline files individually (for example existing LICENSE/Procfile/render.yaml if main lacks Karnish's baseline); keep unrelated PLAN notes, snapshots and artifacts out. No data/processed real file is delivered here. Once the staged change is correct:

```bash
git commit -m "Add core science API and guarded explanations"
git push -u origin adrian/core-api-ai
gh pr create --base main --head adrian/core-api-ai --title "Add core science API and guarded explanations" --body-file docs/implementation/pr-description.md
```

Without gh, open the repository in the browser, choose **Compare & pull request**, base main / compare adrian/core-api-ai, and use pr-description.md for the body. Request Karnish's review of shared integration. This does not grant permission to merge; merge after team review and required checks.

## Add five teammates

Repository **Settings → Collaborators → Add people** (or the matching access-management screen). Invite the actual GitHub accounts belonging to Karnish, Sritharan, Aadarsh, Kavin and Sri Prasath. Account usernames were not provided; do not guess them. Give normal collaborator write access, and have them accept their invitations.

## Protect main

In **Settings → Branches**, add a branch protection rule matching main. Require a pull request before merging, enable required approvals and set **1** approval. Keep force pushes and deletions disabled. Save the rule. If the repository uses rulesets instead, configure equivalent main-branch rules. Require the existing **backend tests** workflow check after GitHub has reported it for the branch. The workflow is preserved from current main; this local delivery does not claim a remote GitHub run.

Use adrian/... feature branches for your changes. Other members should use their own named branches and PRs. Resolve scientific/contract questions through docs/decisions.md and team sign-off, preserving the contract-version process.

Official GitHub guidance: [protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches) and [managing a branch protection rule](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/managing-a-branch-protection-rule).
