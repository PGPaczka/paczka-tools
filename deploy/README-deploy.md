# Synapse — Raspberry Pi Deployment Guide

Deploying Synapse to a headless Raspberry Pi 5 running Debian/Ubuntu.
The RPi co-hosts a Minecraft server, so the design keeps idle load at zero:
the generator runs only on `git push`, never as a daemon.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Raspberry Pi 5 running Debian 12 / Ubuntu 24.04 | Headless; SSH access assumed |
| `git` | `apt install git` |
| `caddy` | See [caddyserver.com/docs/install](https://caddyserver.com/docs/install) for the official Debian/Ubuntu repo |
| .NET runtime | **Not needed** — the generator is published as a self-contained linux-arm64 binary |
| WireGuard | Assumed to be configured separately for homelab access; Caddy listens on plain HTTP `:80` inside the private network |

---

## Directory layout

```
/opt/synapse/
├── vault.git/              bare git repository (receives pushes from vault devices)
│   └── hooks/
│       └── post-receive    ← installed from deploy/post-receive
├── vault/                  checked-out vault files (managed by the hook)
├── viewer/                 Svelte SPA static files (built from synapse-viewer/)
│   ├── index.html
│   ├── assets/
│   ├── graph.json          ← written atomically by the generator on every push
│   └── search-index.json   ← written atomically alongside graph.json (full-text search)
├── Synapse.Generator       self-contained linux-arm64 binary
├── generator.config.json   ← copied from deploy/generator.config.production.json
├── generate.sh             ← pull-and-regenerate script (Forgejo flow only)
└── synapse-webhook.py      ← webhook receiver (Forgejo flow only)
```

---

## Step-by-step setup

### 1. Create the directory structure

```bash
sudo mkdir -p /opt/synapse/vault /opt/synapse/viewer
sudo chown -R $USER:$USER /opt/synapse
```

### 2. Initialise the bare git repository

```bash
git init --bare /opt/synapse/vault.git
```

Vault devices (desktop, laptop, mobile via Working Copy) push to this repo:

```bash
# On each vault device — add once
git remote add pi git@rpi:/opt/synapse/vault.git
```

### 3. Install the post-receive hook

```bash
cp deploy/post-receive /opt/synapse/vault.git/hooks/post-receive
chmod +x /opt/synapse/vault.git/hooks/post-receive
```

Override defaults by setting environment variables in the hook file's config
block, or by placing an environment file at `/etc/synapse/environment` and
sourcing it at the top of the hook (see comments in `deploy/post-receive`).

### 4. Install the generator binary

Build a self-contained linux-arm64 binary on your dev machine:

```bash
cd Synapse.Generator
dotnet publish -c Release -r linux-arm64 --self-contained -o publish/arm64
```

Copy to the RPi:

```bash
scp Synapse.Generator/publish/arm64/Synapse.Generator pi@rpi:/opt/synapse/Synapse.Generator
ssh pi@rpi chmod +x /opt/synapse/Synapse.Generator
```

### 5. Install the generator config

```bash
cp deploy/generator.config.production.json /opt/synapse/generator.config.json
```

Edit `/opt/synapse/generator.config.json` on the RPi to match your vault's
actual frontmatter field names (category, level, status, etc.).

### 6. Deploy the viewer

Build the Svelte SPA on your dev machine:

```bash
cd synapse-viewer
npm install
npm run build
```

Copy the output to the RPi:

```bash
rsync -av synapse-viewer/dist/ pi@rpi:/opt/synapse/viewer/
```

> **Note:** Re-deploying the viewer is only needed when `synapse-viewer/` source
> changes — NOT on every vault push. Vault pushes only update `graph.json`.

### 7. Initial vault checkout

After the first push (or to set up an initial state), run once on the RPi:

```bash
git --git-dir=/opt/synapse/vault.git --work-tree=/opt/synapse/vault checkout -f main
```

Subsequent pushes trigger the post-receive hook, which runs the same checkout
command automatically.

### 8. Configure Caddy

```bash
# If /etc/caddy/Caddyfile is empty / fresh:
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile

# If you have an existing Caddyfile, append an import or paste the site block.
# Then reload:
sudo systemctl reload caddy
```

The Caddyfile serves the viewer SPA on `:80` with:
- `Cache-Control: no-cache` for `graph.json` (viewer ETag-checks on load)
- `Cache-Control: max-age=31536000, immutable` for fingerprinted Vite assets

---

## First-push smoke test

```bash
# From any vault device that has the pi remote set up
git push pi main
```

Then on the RPi:

```bash
# Confirm the hook ran
tail -20 /var/log/synapse-generator.log

# Confirm graph.json was written
ls -lh /opt/synapse/viewer/graph.json

# Visit the viewer in a browser (on the WireGuard network)
# http://<rpi-wireguard-ip>/
```

Expected log output:

```
[2026-…Z] INFO  ── Synapse generation started ──────────────────────────────
[2026-…Z] INFO  Checking out 'main' to /opt/synapse/vault
[2026-…Z] INFO  Running generator: /opt/synapse/Synapse.Generator
[2026-…Z] INFO  Generated graph.json: 42 nodes (3 ghosts), 87 edges
[2026-…Z] INFO  Generated search-index.json: 42 entries
[2026-…Z] INFO  graph.json written to /opt/synapse/viewer/graph.json (2s)
[2026-…Z] INFO  ── Synapse generation complete ─────────────────────────────
```

---

## Concurrent push behaviour

If two devices push simultaneously, the second push will log a warning and exit
without running the generator:

```
[2026-…Z] WARN  Generator already running (lock held: /tmp/synapse-generator.lock). Skipping this push.
[2026-…Z]       The graph.json from the in-progress run remains valid.
```

The `graph.json` produced by the first push remains valid; no data is lost.
The lock file is `/tmp/synapse-generator.lock` and is auto-released when the
generator process finishes (file descriptor close releases `flock`).

---

## Local simulation test

Use `deploy/test-local-push.sh` to verify the full push pipeline on your dev
machine before deploying to the RPi:

```bash
# Uses the built-in test fixture vault
./deploy/test-local-push.sh

# Or point at a custom vault directory
./deploy/test-local-push.sh /path/to/my/vault
```

The script:
1. Creates a temp bare repo and checkout directory under `/tmp/`.
2. Installs the post-receive hook, wired to the locally published generator binary.
3. Initialises a git repo from the fixture vault and pushes it to the bare repo.
4. Asserts that `graph.json` was created.
5. Prints the hook log and cleans up on exit.

Prerequisites for the test script:

```bash
# Build a local (linux-x64 or native) binary first
cd Synapse.Generator
dotnet publish -c Release -r linux-x64 --self-contained -o publish
```

---

## WireGuard note

WireGuard configuration is outside the scope of this guide. The assumption is
that the RPi has a WireGuard interface (`wg0`) and that vault devices and the
browser client are peers on the same WireGuard network. Caddy listens on plain
HTTP `:80`; all traffic is encrypted by WireGuard at the network layer.

If you need HTTPS (e.g. for a public endpoint or iOS shortcut integration),
uncomment the TLS variant block in `deploy/Caddyfile` and configure a hostname.

---

## Forgejo-as-intermediary (optional)

The setup above has vault devices push **directly** to the RPi's bare git repo
(`vault.git`). If you prefer to keep Forgejo as the canonical remote and have
the RPi pull from it, this section describes how.

**Flow:**

```
vault devices ──push──▶ Forgejo ──webhook──▶ RPi /hook ──▶ generate.sh
                                                            (git pull + generate)
                         cron (every 5 min) ──▶ generate.sh  (fallback)
```

Both mechanisms call the same `generate.sh` script. The webhook gives instant
updates on push; cron is a safety net in case a webhook delivery is missed.

### Prerequisites for this flow

- The RPi has SSH or HTTPS access to the Forgejo repo.
- The Forgejo instance can reach the RPi's WireGuard IP on port 80
  (the webhook is proxied through Caddy — no extra port needed).

---

### Step F1. Clone the vault from Forgejo

```bash
# On the RPi — replace the URL with your Forgejo repo
git clone https://forgejo.example.com/user/vault.git /opt/synapse/vault
```

> If using SSH: `git clone git@forgejo.example.com:user/vault.git /opt/synapse/vault`
>
> For SSH, make sure the RPi's key is added to Forgejo under the relevant account.

---

### Step F2. Install generate.sh

```bash
cp deploy/generate.sh /opt/synapse/generate.sh
chmod +x /opt/synapse/generate.sh
```

Test it manually once:

```bash
/opt/synapse/generate.sh
tail -20 /var/log/synapse-generator.log
ls -lh /opt/synapse/viewer/graph.json /opt/synapse/viewer/search-index.json
```

---

### Step F3. Set up the cron job (A — periodic fallback)

```bash
crontab -e
```

Add the following line (runs every 5 minutes):

```
*/5 * * * * /opt/synapse/generate.sh >> /var/log/synapse-generator.log 2>&1
```

The `flock`-based lock inside `generate.sh` ensures the cron and webhook never
run the generator simultaneously; the second caller logs a warning and exits.

---

### Step F4. Configure the webhook receiver (B — instant trigger)

#### 4a. Create the environment file

```bash
sudo mkdir -p /etc/synapse
sudo tee /etc/synapse/webhook.env > /dev/null <<'EOF'
SYNAPSE_WEBHOOK_SECRET=change-me-to-a-random-string
SYNAPSE_WEBHOOK_PORT=9000
SYNAPSE_GENERATE_SH=/opt/synapse/generate.sh
EOF
sudo chmod 600 /etc/synapse/webhook.env
```

Generate a random secret (copy the output into `webhook.env`):

```bash
openssl rand -hex 32
```

#### 4b. Install the receiver script and systemd service

```bash
cp deploy/synapse-webhook.py /opt/synapse/synapse-webhook.py
cp deploy/synapse-webhook.service /etc/systemd/system/synapse-webhook.service
```

Edit the service file if the RPi's username is not `pi`:

```bash
sudo nano /etc/systemd/system/synapse-webhook.service
# Change: User=pi  →  User=<your-user>
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now synapse-webhook
sudo systemctl status synapse-webhook
```

Check the receiver is listening:

```bash
journalctl -u synapse-webhook -n 20
# Expected: "Synapse webhook receiver on 127.0.0.1:9000"
```

#### 4c. Update Caddy

The `deploy/Caddyfile` already includes the `/hook` route that proxies to the
receiver. If you copied the Caddyfile before this change, add the block manually:

```caddy
handle /hook {
    reverse_proxy localhost:9000
}
```

Place it **before** the `handle { file_server ... }` block, then reload:

```bash
sudo systemctl reload caddy
```

#### 4d. Add the webhook in Forgejo

In Forgejo → your vault repo → **Settings → Webhooks → Add Webhook → Gitea**:

| Field | Value |
|---|---|
| Target URL | `http://<rpi-wireguard-ip>/hook` |
| HTTP Method | POST |
| Content type | `application/json` |
| Secret | (paste the value from `webhook.env`) |
| Trigger | `Push events` only |

Save and use **Test Delivery** to verify the webhook fires and the RPi logs show
a generation run.

---

### Smoke test (Forgejo flow)

```bash
# Push a small change to Forgejo from any vault device
echo "test" >> /path/to/vault/any-note.md
git -C /path/to/vault commit -am "test webhook" && git push origin main

# On the RPi, confirm within a few seconds:
tail -f /var/log/synapse-generator.log
```

Expected log (same format as the direct-push flow):

```
[2026-…Z] INFO  ── Synapse generation started ──────────────────────────────
[2026-…Z] INFO  Fetching origin/main into /opt/synapse/vault
[2026-…Z] INFO  Running generator: /opt/synapse/Synapse.Generator
[2026-…Z] INFO  Generated graph.json: 42 nodes (3 ghosts), 87 edges
[2026-…Z] INFO  Generated search-index.json: 42 entries
[2026-…Z] INFO  graph.json + search-index.json written (2s)
[2026-…Z] INFO  ── Synapse generation complete ─────────────────────────────
```
