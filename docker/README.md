# Docker

`Dockerfile` has two targets:

| Target    | Contents                                                | Use                                      |
|-----------|---------------------------------------------------------|------------------------------------------|
| `runtime` | Core requirements: API, PDF/text ingestion, BM25, Chroma | Default; no keys, no model downloads     |
| `ml`      | `runtime` plus the OpenAI client and local-model libraries | Set `--target ml` when you need providers |

```bash
docker build -f docker/Dockerfile --target runtime -t doc-intel .
docker run --rm -p 8000:8000 -v doc-intel-data:/app/data doc-intel
# or
docker compose -f docker/docker-compose.yml up --build
```

`scripts/docker/smoke_test.sh IMAGE` starts a container, uploads a sample
document, runs a lexical search, and stops the container. CI runs it against
the `runtime` target.

No image-size figures are published here; measure with `docker images` if
you need them. The compose file runs only the API: Redis, Prometheus, and
Grafana are not part of the supported path.
