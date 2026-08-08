# Deploying Sentinel on AWS

One EC2 instance running three containers — backend, console, and Caddy in front
of both — with an EBS volume for run history. `docker-compose.yml`, `Dockerfile`,
`frontend/Dockerfile` and `Caddyfile` in this repo are the whole deployment.

---

## Why a single instance, and not something more elastic

Four properties of the backend decide this before any AWS service is chosen:

| Property | Where | Consequence |
|---|---|---|
| Live runs held in a process-local dict | [events.py:90](sentinel/api/events.py#L90) | A second replica owns a different set of runs |
| Each run is a thread parked on an `Event` until `/resume` | [events.py:71](sentinel/api/events.py#L71) | The resume must reach the *same process* |
| SSE held open for the length of a run (~26 min at full effort) | [main.py:132](sentinel/api/main.py#L132) | No request-timeout budget survives it |
| SQLite + Chroma on local disk | [config.py:173](sentinel/config.py#L173) | Needs a real filesystem and one writer |

So: **one always-on task, one replica, one attached disk.** That rules out
Lambda and API Gateway outright, and rules out App Runner and any scale-to-zero
Fargate arrangement. Fargate with EFS would technically run, but SQLite over NFS
is a locking hazard and this app shares one `sqlite3` connection across threads
([repo.py:26](sentinel/store/repo.py#L26)) — EBS on EC2 is simply a disk, with
none of that risk.

Scaling out is a code change, not a deployment one: move run state into the
shared store and swap `InMemorySaver` for `langgraph-checkpoint-sqlite`, which is
already a dependency.

---

## 1. Provision

**Instance.** `t3.medium` (2 vCPU / 4 GiB), Ubuntu 24.04 LTS, x86_64.

4 GiB is the real floor, not padding: Chroma pulls an ONNX embedding model into
memory for the `rag_agent` target, and the Next.js build peaks around 1 GiB. A
`t3.small` will OOM during `docker compose build`.

**Storage.** 30 GiB gp3 root volume. Images plus the embedding model run to
several GiB.

**Security group.**

| Port | Source | Why |
|---|---|---|
| 443 | `0.0.0.0/0` | Console + API |
| 80 | `0.0.0.0/0` | Required — Let's Encrypt validates over it |
| 22 | your IP only | Or omit entirely and use SSM Session Manager |

**Elastic IP.** Allocate one and associate it. Without it the public address
changes on every stop/start and both your DNS record and the issued certificate
go stale.

Cost, if you are watching credits: roughly **$36/month** — ~$30 instance, ~$2.40
volume, ~$3.60 for the public IPv4 address.

## 2. DNS and TLS

Caddy issues and renews the certificate itself; it only needs a name that
resolves to the Elastic IP.

- **With a domain** — a Route 53 (or any registrar) A record to the Elastic IP.
  Set `SITE_ADDRESS=sentinel.example.com`.
- **Without one** — `SITE_ADDRESS=<elastic-ip>.sslip.io`. sslip.io resolves any
  `<ip>.sslip.io` to that IP, and Let's Encrypt will normally issue for it. It is
  a shared domain, so issuance can occasionally hit a rate limit; if that
  happens, fall back to the next option.
- **Private** — `SITE_ADDRESS=:80`, port 80/443 closed in the security group, and
  reach it over an SSH tunnel:
  `ssh -L 8443:localhost:80 ubuntu@<ip>`. No certificate, nothing exposed. For a
  tool that holds a live Anthropic key this is a defensible default.

## 3. Install and configure

```bash
ssh ubuntu@<elastic-ip>

curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
exit && ssh ubuntu@<elastic-ip>          # re-login for the group to apply

git clone <your-repo> sentinel && cd sentinel
cp .env.example .env
```

Edit `.env`:

```bash
ANTHROPIC_API_KEY=sk-ant-...
SENTINEL_PROFILE=dev                     # demo raises the cap to $8 PER RUN
SENTINEL_API_TOKEN=<paste a generated token>
SITE_ADDRESS=sentinel.example.com
SITE_ORIGIN=https://sentinel.example.com
```

Generate the token with:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

`SITE_ORIGIN` must be exactly the origin the browser sees — scheme included, no
trailing slash. It feeds both the CORS allowlist and the console's API base.

## 4. Deploy

```bash
docker compose up -d --build
```

The first build takes several minutes (Chroma's dependency tree). Compose reads
`.env` for both variable interpolation and the backend's environment, so the key
never leaves the instance.

## 5. Verify

```bash
BASE=https://sentinel.example.com
TOKEN=$(grep '^SENTINEL_API_TOKEN=' .env | cut -d= -f2)

curl -fsS $BASE/api/healthz                                   # 200, public
curl -o /dev/null -w '%{http_code}\n' $BASE/api/health        # expect 401
curl -fsS -H "X-Sentinel-Token: $TOKEN" $BASE/api/health      # 200 + config
```

Then a full pipeline with no key and no spend, from inside the instance:

```bash
docker compose exec -e SENTINEL_FAKE_LLM=1 backend \
  python scripts/e2e_http.py \
    --base http://127.0.0.1:8000 \
    --target support_bot --quiet
```

Open `$BASE` and confirm the console loads and streams. Only then set
`SENTINEL_FAKE_LLM=0` and run for real.

---

## Pointing Sentinel at a target

The endpoint is not configured at deploy time — it is a field on the **scope**,
submitted through the console's authorization form (`POST /scopes`) and frozen
into the scope's signed hash ([models.py:51](sentinel/scope/models.py#L51)).
Every run resolves its target from there.

**The three built-in targets** are served by the backend itself at
`/targets/{id}/chat`, so the endpoint to enter is the backend's own loopback
address:

```
http://127.0.0.1:8000/targets/support_bot/chat
```

Loopback specifically, not the public URL. The harness attaches its API token
only to loopback targets ([transport.py:31](sentinel/graph/transport.py#L31)) —
`target_endpoint` is operator-supplied and may name a system you are attacking,
and sending Sentinel's own token there would hand that host the key to the
auditor. A public URL in this field returns 401 and the run reports the target as
unreachable.

**A third-party agent** must speak the same wire shape, since `send_to_target` is
a plain HTTP POST ([base.py:3](sentinel/targets/base.py#L3)):

```
POST <endpoint>
  → {messages, session_id, attack_id, turn, system_suffix, model}
  ← {text, tool_calls, retrieved_docs, error}
```

Almost nothing speaks this natively, so in practice you write a small adapter
that translates to the agent's own API and expose that as the endpoint.

Two features degrade against a black-box target, and it is worth knowing before
you demo them:

- **Fix-and-reverify** needs `system_suffix` to append a mitigation to the
  target's system prompt. An endpoint that will not accept prompt injection from
  its caller cannot be patch-tested this way.
- **Differential audit** needs `model` to swap the model behind the same harness.

Both are exercised fully against the built-in targets, which do honour those
fields.

---

## Operating notes

**A restart kills in-flight runs.** The checkpointer is in-memory
([events.py:124](sentinel/api/events.py#L124)), so any `docker compose up -d
--build`, OOM, or instance reboot loses runs in progress. Finished reports are in
SQLite and survive. Redeploy when nothing is running.

**Back up the volume.** Run history, findings, and the self-extending technique
KB all live in `sentinel-data`:

```bash
docker compose exec backend sqlite3 /data/sentinel.db ".backup /data/backup.db"
docker compose cp backend:/data/backup.db ./sentinel-backup.db
```

An EBS snapshot schedule on the root volume covers the same ground.

**Run the CI gate on the instance, not your laptop.** `sentinel ci` executes
in-process and reaches the target over HTTP, so it needs both loopback access and
the token in its environment:

```bash
docker compose exec backend sentinel ci --baseline /data/baseline.json
```

Run from a laptop it fails twice over — the report's `target_endpoint` is a
loopback address the laptop cannot reach, and without `SENTINEL_API_TOKEN` in the
environment the call is unauthenticated. The failure is quiet rather than loud:
findings come back `unevaluated` with "target returned no usable response".

**Rotating the token or moving the API needs a frontend rebuild.** Both
`NEXT_PUBLIC_*` values are compiled into the client bundle by `next build`
([api.ts:14](frontend/lib/api.ts#L14)). Setting them at container runtime does
nothing:

```bash
docker compose up -d --build frontend
```

**Watch the budget.** `SENTINEL_PROFILE=demo` caps a run at $8 — per run, with no
limit on how many runs are started. The token is what stands between the internet
and that spend.

---

## What this deployment does not give you

The token is a **shared secret, not an identity**. It is compiled into the client
bundle and readable by anyone who opens devtools on the console. It keeps the API
from being open to whoever finds the hostname; it does not tell you who started a
run, and it cannot be revoked per-person.

If you need real identity — several operators, an audit trail of who authorized
which scope — put an identity-aware proxy in front of the whole origin rather
than extending this scheme. AWS Application Load Balancer with Cognito
authentication, or Cloudflare Access, both terminate in front of Caddy and need
no application change. Configure either to leave `text/event-stream` responses
unbuffered, or the run stream will appear to hang.
