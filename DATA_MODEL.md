# Data Model

This document is a placeholder for a human-readable data model and/or data catalog document. The objective is to plan the data model to be “scalable, logical, resource efficient, extensible, and discoverable”. By planning now, future use cases, workflows and supported platforms can come online without forcing potentially expensive and error-prone migrations. It should take ROADMAP.md into account, and enhancements listed in BUGS.md, but those should not be considered comprehensive for all time (i.e. ask questions about future use cases)

The data model should account for objects in the application, and files on disk. For each object/file type, the model should define:
- How it is derived/discovered
- Whether it should be treated as mutable or immutable and how that gets enforced (fs permissions, in-app handling, etc)
- Whether it is ephemeral or persistent
- If ephemeral, how long it is/should be retained, and how it gets cleaned up or cycled
- Other attributes as appropriate

If there is an object hierarchy (i.e. objects inherit attributes from higher-level objects) that should be spelled out and/or diagrammed.