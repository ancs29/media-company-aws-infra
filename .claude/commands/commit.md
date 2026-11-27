---
description: Commit all changes and push with the given message
argument-hint: <commit message>
---

Commit and push the repo with this message: $ARGUMENTS

If no message was given, ask for one and do nothing else. Otherwise run, as one command, with the
message single-quoted (escape any `'` in it):

```bash
git add -A && git commit -m '<message>' && git push
```
