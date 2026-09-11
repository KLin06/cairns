# Cairns

Trail conditions app: a Postgres-backed FastAPI server (`server/`), a
Vite/React client (`client/`), and a separate ML data/training pipeline
(`data/`) that produces the trail-conditions prediction model.

**Live (WIP):** [cairns-five.vercel.app](https://cairns-five.vercel.app/) —
client on Vercel, backend on Render. Still under active development, expect
rough edges.

See `APP_SPEC.md` for the product/API spec, and `server/README.md` /
`client/README.md` for each service's own docs.

## Running with Docker

```bash
cp .env.example .env   # fill in real values, see comments in the file
docker compose up --build
```

Brings up Postgres, the API server, and the client together. The server
fetches its prediction model from S3 rather than a local file - see
`specs/007-docker-containerization/quickstart.md` for a full walkthrough
and `specs/007-docker-containerization/contracts/env-vars.md` for what
every variable in `.env.example` does. `data/` (the training pipeline) is
run separately/manually and isn't part of this compose stack.
