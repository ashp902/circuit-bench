# Circuit Bench production deployment

## Production architecture

Circuit Bench deploys as one Docker service:

- A Node build stage installs frontend dependencies and creates the Next.js static export.
- A Python runtime stage installs backend dependencies and the real `ngspice` executable.
- FastAPI serves the exported frontend, `/api/*`, `/health`, and `/api/webmcp/*` from one origin.
- One Uvicorn process binds to `0.0.0.0:$PORT`.
- SQLite is stored at `LAB_DB_PATH`; production defaults to `/data/lab.db`.
- Anonymous visitors are isolated by a secure HttpOnly cookie whose server-side mapping is stored in the same persistent SQLite database.

The single-origin layout requires no production CORS allowance and preserves the same relative API and WebMCP invocation paths used locally. Run one service replica: a single SQLite database on one attached disk is canonical and is not intended for horizontal multi-writer scaling.

## Environment variables

| Variable | Railway/Render value | Required | Purpose |
| --- | --- | --- | --- |
| `LAB_ENV` | `production` | Yes | Enables production-safe defaults. |
| `LAB_DB_PATH` | `/data/lab.db` | Yes | Places SQLite on the mounted persistent volume. |
| `NGSPICE_BIN` | `/usr/bin/ngspice` | Recommended | Uses the binary installed in the image. |
| `LAB_FRONTEND_DIR` | `/app/static` | No | Already set by the Docker image. |
| `LAB_CORS_ORIGINS` | empty | No | Same-origin production needs no CORS. Set a comma-separated HTTPS allowlist only if a separate frontend is introduced. |
| `LAB_CLEANUP_INACTIVE_SESSIONS` | `false` | No | Set to `true` to delete anonymous Labs unused for more than 30 days when the service starts. |
| `PORT` | platform supplied | No | Railway and Render inject this. Do not hardcode it in the platform settings. |

`NEXT_PUBLIC_API_BASE_URL` is intentionally empty at image build time, so browser calls use the deployed page's own HTTPS origin. None of these variables is a secret. Do not commit platform tokens or credentials.

`LAB_DATABASE_URL` remains accepted for backwards compatibility, but new deployments should use `LAB_DB_PATH`.

## Deploy to Railway from GitHub

1. Push this repository to GitHub.
2. In Railway, choose **New Project → Deploy from GitHub repo**, authorize the repository if needed, and select Circuit Bench.
3. Keep the service root at the repository root. Railway detects the root `Dockerfile`; `railway.json` also declares the Dockerfile, `/health` check, and restart policy.
4. Before relying on the service for data, open the service and add a persistent volume. Attach it to this service with the exact mount path `/data`.
5. In **Variables**, set:

   ```text
   LAB_ENV=production
   LAB_DB_PATH=/data/lab.db
   NGSPICE_BIN=/usr/bin/ngspice
   LAB_CORS_ORIGINS=
   ```

   Do not add `PORT`; Railway supplies it. The Docker image already sets `LAB_FRONTEND_DIR=/app/static`.
6. Keep the service at one replica. Deploy and confirm the `/health` check becomes healthy.
7. In **Settings → Networking**, choose **Generate Domain**. Railway provisions the public domain and TLS certificate. To use a custom domain, add it there and follow Railway's displayed DNS record instructions.
8. Open `https://<generated-domain>/health`; it must return:

   ```json
   {"status":"ok","service":"electronics-lab-api"}
   ```

9. Complete the production smoke checklist below. Restart or redeploy once after saving a circuit and confirm it remains present.

The volume must be attached before production data is created. Container-local files outside `/data` are ephemeral. Configure Railway volume backups according to the project's recovery requirements.

## Render fallback

The same image works on Render. The included `render.yaml` can create the service and its disk as a Blueprint, or configure it manually:

1. In Render, create a **Web Service**, connect the GitHub repository, and select the **Docker** runtime.
2. Use `./Dockerfile` from the repository root.
3. Add a persistent disk named `circuit-bench-data`, mounted at `/data`, with at least 1 GB. Persistent disks require a paid Render instance.
4. Set the same variables used on Railway:

   ```text
   LAB_ENV=production
   LAB_DB_PATH=/data/lab.db
   NGSPICE_BIN=/usr/bin/ngspice
   LAB_CORS_ORIGINS=
   ```

5. Set the health-check path to `/health`. Do not set `PORT`; Render supplies it.
6. Deploy, use the generated `onrender.com` HTTPS URL or add a custom domain, and complete the smoke checklist.

Keep one Render instance. A service with an attached persistent disk does not receive Render's zero-downtime deploy behavior, so expect a brief interruption while a new deploy starts and remounts the disk.

## Local production verification

### Docker image

Docker is the closest match to Railway and Render:

```bash
docker build -t circuit-bench:production .
docker volume create circuit-bench-data
docker run --rm --name circuit-bench \
  -p 8000:8000 \
  -e PORT=8000 \
  -e LAB_ENV=production \
  -e LAB_DB_PATH=/data/lab.db \
  -v circuit-bench-data:/data \
  circuit-bench:production
```

In another terminal:

```bash
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8000/api/webmcp/tools
open http://127.0.0.1:8000
```

Stop the container, run the same `docker run` command again, and confirm saved circuits and experiments remain. The named volume is intentionally retained. Remove it only when you explicitly intend to erase the production-test database.

### Production process without Docker

This verifies the single-process layout when Docker is unavailable, but the host must already have Node.js, Python dependencies, and `ngspice` installed:

```bash
cd frontend
NEXT_OUTPUT_MODE=export NEXT_PUBLIC_API_BASE_URL= npm run build

cd ../backend
LAB_ENV=production \
LAB_DB_PATH=/tmp/circuit-bench/lab.db \
LAB_FRONTEND_DIR="$PWD/../frontend/out" \
PORT=8000 \
.venv/bin/python -m app.production
```

## Production smoke-test checklist

Run this against the final public HTTPS domain:

- [ ] The application loads without mixed-content, CORS, or browser-console errors.
- [ ] `GET /health` returns HTTP 200 and `status: ok`.
- [ ] Create a blank circuit and rename it.
- [ ] Add components, move them, connect their terminals, and verify autosave.
- [ ] Validate the circuit and receive a real validation result.
- [ ] Run an operating-point simulation and inspect its values.
- [ ] Run an AC sweep and confirm magnitude and non-flat phase results.
- [ ] Run a transient simulation and inspect the waveform.
- [ ] Confirm simulation responses identify real `ngspice` execution; no fallback or fabricated result is accepted.
- [ ] Create an experiment with structured measurements and requirements, generate its plan, execute the full matrix, and inspect persisted PASS/FAIL results and worst-case analysis.
- [ ] Create or edit a saved circuit, restart/redeploy the service, then confirm that circuit and its run history survive from `/data/lab.db`.
- [ ] In a native WebMCP-capable HTTPS browser, confirm the browser's site-tools indicator appears for the page.
- [ ] Confirm `GET /api/webmcp/tools` returns the complete non-empty tool list.
- [ ] Ask an agent to discover the page's registered tools and invoke a read tool, a circuit mutation, and a real simulation successfully.

If the backend tool endpoint works but the browser does not show site tools, check that the page is loaded over HTTPS and test with a browser build that implements native `document.modelContext`. Do not add a polyfill or change tool semantics to compensate for an unsupported browser.

## Platform references

- Railway: [Dockerfiles](https://docs.railway.com/builds/dockerfiles), [volumes](https://docs.railway.com/volumes), and [public domains](https://docs.railway.com/networking/public-networking)
- Render: [Docker services](https://render.com/docs/docker), [persistent disks](https://render.com/docs/disks), and [health checks](https://render.com/docs/health-checks)
