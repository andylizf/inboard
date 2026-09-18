`administration` is not a workflow permission scope. The list `actionlint` prints, which is the same list in GitHub's workflow-syntax docs, holds sixteen names and not that one:

```
$ actionlint .github/workflows/box-uptime.yml
.github/workflows/box-uptime.yml:16:3: unknown permission scope "administration".
all available permission scopes are "actions", "artifact-metadata", "attestations",
"checks", "contents", "deployments", "discussions", "id-token", "issues", "models",
"packages", "pages", "pull-requests", "repository-projects", "security-events",
"statuses" [permissions]
```

GitHub does not ignore the unknown key. It refuses to parse the file, and a file it cannot parse is a file that does not run. Since #1083 landed at 05:02Z every push to main has produced a `box-uptime` run with zero jobs, zero seconds and no log (runs 35184212343 and 35184418516), and nothing in this file runs on its schedule any more. The heartbeat-age check and the `dev-health` probe live here too, so they went with it. No check on the PR page said so, because `box-uptime` is not one of the checks a PR runs.

## The runner list still needs a token this one is not

Deleting the line does not buy the API call back. "List self-hosted runners for a repository" states that the caller must have admin access to the repository, and the workflow token cannot be granted it. `box-heartbeat.yml` already records the same finding about the check `ci-pool` replaces: it failed every single time from the day it was created, for this reason.

So `ci-pool` gets a 403 until someone hands it a token that has that access. The 403 branch used to print a warning and return 0, which is a check that has never looked at anything reporting a healthy pool. It exits red now.

## What the team hears

Red is honest. Paging the team over it is not. `ci-pool-health.py` writes the `problems` output only when it has actually named a machine, so the Feishu step is gated on that as well as on `failure()`. Without it, "CI 机器掉了：见运行日志" goes out twice an hour from a check that could not read the pool, and that is how an alert channel becomes one people ignore.

## Checks

`actionlint` is clean on the file, and `python3 -m unittest discover -s .github/scripts` passes, 20 tests.
