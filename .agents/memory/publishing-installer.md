---
name: Publishing installer limits
description: Limits of diagnosing automatic Python package installation from production settings.
---

Do not assume a saved production environment setting reaches or controls the automatic dependency-install phase. A project-local pip config can override the installer's user-mode default.

**Why:** A new publish still rejected a user-mode pip install despite a confirmed production `PIP_USER=false` setting. Pip reads the project's `.config/pip/pip.conf`, but this location may be globally ignored by Git and must be tracked for publishing. The same application, requirements, runtime module, and deployment command had previously published successfully.

**How to apply:** Configure `user = false` in `.config/pip/pip.conf`, ensure the file is included in the published source, and inspect a fresh build's logs. Passing app tests and a working preview do not validate publishing.
