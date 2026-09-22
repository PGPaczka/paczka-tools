---
title: Dockerfile
category: DevOps
level: 1
status: completed
tags: [containers, docker]
---

A Dockerfile defines the image build steps. Requires [[docker-basics]].

Example:

```dockerfile
FROM ubuntu:22.04
# [[not-a-link]] inside code block — must NOT be extracted
RUN apt-get update
```

Keep layers small for fast builds.
