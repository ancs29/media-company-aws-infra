---
description: Run the cleanup subagent on changed .py files (default uncommitted; or pass a git ref)
argument-hint: "[git ref, e.g. HEAD~3 or main]"
---

Spawn the `cleanup` subagent with the Agent tool. Pass it only the scope below, and none of your
own context about why the code was written, so it reviews the code with fresh eyes.

Scope: $ARGUMENTS

(An empty scope means uncommitted changes only.)

Don't summarise or relay its changes. Reply with one line saying the cleanup finished, or that it
failed and why.
