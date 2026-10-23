---
name: Publishing installer limits
description: Limits of diagnosing automatic Python package installation from production settings.
---

Do not assume a saved production environment setting reaches or controls the automatic dependency-install phase.

**Why:** A new publish still rejected a user-mode pip install despite a confirmed production `PIP_USER=false` setting. The same application, requirements, runtime module, and deployment command had previously published successfully. The exact source of the forced user-install mode was not established.

**How to apply:** Inspect the newest build logs after a retry. Passing app tests and a working preview do not validate publishing. Avoid repeating the ineffective setting or making unrelated application changes; investigate the build environment or report the blocker.
