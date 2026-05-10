# OpenHands + OpenRouter + Docker + Claude Haiku on WSL

> A complete setup guide for running a local AI coding agent on Windows using WSL, Docker Desktop, OpenRouter, and Claude 3.5 Haiku. Includes all known installation traps.

---

## How the Stack Connects

| Component | Role |
|---|---|
| **WSL (Ubuntu)** | Linux environment running inside Windows |
| **Docker Desktop** | Sandbox runtime — OpenHands runs all AI-generated code here safely |
| **OpenHands** | Open-source AI coding agent (UI + backend) |
| **OpenRouter** | API gateway to access Claude cheaply |
| **Claude 3.5 Haiku** | The LLM brain doing the thinking |

---

## Part 1 — Windows Prerequisites

### 1.1 Install WSL2
In PowerShell (run as Administrator):
```powershell
wsl --install
```
Reboot when prompted. This installs Ubuntu by default.

### 1.2 Install Docker Desktop
Download from: https://www.docker.com/products/docker-desktop/

> ⚠️ **TRAP — WSL Integration must be enabled**
> After installing, go to Docker Desktop → **Settings → Resources → WSL Integration**
> - Enable "Use the WSL 2 based engine"
> - Enable "Enable integration with my default WSL distro"
>
> Without this, Docker commands inside WSL will fail with "command not found".

### 1.3 Create an OpenRouter Account
- Sign up at https://openrouter.ai
- Get your API key at https://openrouter.ai/keys (starts with `sk-or-v1-...`)
- Add a small credit balance ($5 is plenty — Haiku costs ~$0.001/task)

---

## Part 2 — WSL Setup (inside Ubuntu terminal)

### 2.1 Install Node.js via nvm

> ⚠️ **TRAP — Do NOT use `apt install nodejs`**
> The apt package manager installs Node.js v12, which is far too old. The OpenHands frontend build will fail with cryptic errors. Always use `nvm` instead.

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
source ~/.bashrc
nvm install --lts
nvm use --lts
node --version   # should show v20+
npm --version
```

### 2.2 Install Python uv
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
uv --version
```

### 2.3 Clone and Install OpenHands
```bash
git clone https://github.com/All-Hands-AI/OpenHands.git ~/openhands
cd ~/openhands
uv sync
cd frontend && npm install && cd ..
```

---

## Part 3 — Starting OpenHands (Every Session)

> ⚠️ **TRAP — Start Docker Desktop FIRST**
> Always open Docker Desktop on Windows and wait until the whale icon in the taskbar says "Docker is running" **before** starting OpenHands.
> If Docker is closed, the backend starts fine but every "New Conversation" returns a 500 error.

Open **two WSL terminals**:

**Terminal 1 — Backend:**
```bash
cd ~/openhands
uv run python -m openhands.server
```
✅ Ready when you see: `Uvicorn running on http://0.0.0.0:3000`

**Terminal 2 — Frontend:**
```bash
cd ~/openhands/frontend
npm run dev
```
✅ Ready when you see: `Local: http://localhost:3001`

Open your browser at **http://localhost:3001**

---

## Part 4 — Configure OpenRouter LLM Profile

In the OpenHands UI go to **Settings → LLM → Add Profile**, select the **"All"** tab and fill in:

| Field | Value |
|---|---|
| Name | `openrouter-haiku` |
| Custom Model | `openrouter/anthropic/claude-3-5-haiku` |
| Base URL | `https://openrouter.ai/api/v1` |
| API Key | your key (`sk-or-v1-...`) |

Leave all other fields (API Version, AWS fields) blank.

> ⚠️ **TRAP — Base URL must be set**
> The Base URL MUST be `https://openrouter.ai/api/v1`. Do not leave it as the default placeholder or blank — requests will fail silently.

Click **Save Changes**, then **Activate** the profile.

---

## Part 5 — Fix Docker Sandbox Image (First Time Only)

When you first click "New Conversation", OpenHands pulls a Docker sandbox image. The version-tagged image may not exist on the registry yet.

> ⚠️ **TRAP — Image tag not found**
> You may see: `ghcr.io/openhands/agent-server:X.XX.X-python: not found`
>
> **Fix:** Pull `latest-python` and retag it locally.

```bash
# Replace 1.21.0-python with whatever version your backend logs show
docker pull ghcr.io/openhands/agent-server:latest-python
docker tag ghcr.io/openhands/agent-server:latest-python ghcr.io/openhands/agent-server:1.21.0-python
```

Then restart the backend (Ctrl+C in Terminal 1, re-run the command) and try New Conversation again.

> ⚠️ **TRAP — Image pull looks like a hang**
> The image is ~4–6 GB. The terminal may appear frozen for 1–2 minutes before progress bars appear. The UI will return 500 errors the entire time it is downloading. This is normal — just wait.

---

## Part 6 — Set OpenRouter Spending Limits

Go to: https://openrouter.ai/settings/limits

| Setting | Value |
|---|---|
| Soft Limit | `$3` — email warning |
| Hard Limit | `$5` — all calls stop automatically |

---

## Part 7 — Verify Everything Works

In the OpenHands chat box, type:

> Write a Python script that prints "Hello from Claude Haiku!" and today's date and time. Then run it.

You should see OpenHands think, write the file, execute it in Docker, and return the output. ✅

---

## Part 8 — Accessing Files OpenHands Creates

Files are created **inside the Docker container** at `/workspace/project/` — they are not on your WSL filesystem directly.

> ⚠️ **TRAP — `$(docker ps -q)` fails with multiple containers**
> Always run `docker ps` first and copy the explicit container ID from the `oh-agent-server` row.

```bash
# Step 1 — find the container ID
docker ps

# Step 2 — list files inside the sandbox
docker exec <CONTAINER_ID> ls /workspace/project/

# Step 3 — copy a file out to your WSL home
docker cp <CONTAINER_ID>:/workspace/project/myfile.py ~/myfile.py
```

---

## Startup Checklist (Every Session)

- [ ] Docker Desktop is open and running on Windows (whale icon = green)
- [ ] Terminal 1: backend started, shows Uvicorn on port 3000
- [ ] Terminal 2: frontend started, shows localhost:3001
- [ ] Browser open at http://localhost:3001
- [ ] `openrouter-haiku` profile is active (shown in the chat toolbar)

---

## Trap Summary

| Trap | Symptom | Fix |
|---|---|---|
| `apt install nodejs` used | Frontend build fails | Use `nvm install --lts` |
| Docker Desktop not running | 500 on New Conversation | Start Docker Desktop first |
| WSL integration not enabled | `docker: command not found` in WSL | Enable in Docker → Settings → WSL Integration |
| Image tag not found | 500 on New Conversation | Pull `latest-python`, retag to version backend expects |
| Image still downloading | 500 errors for 5–15 mins | Wait for pull to complete |
| Base URL not set | LLM calls fail silently | Set to `https://openrouter.ai/api/v1` |
| `docker ps -q` returns multiple IDs | `exec` fails | Use explicit container ID from `docker ps` |
| Looking for files on WSL filesystem | Files not found | Files are inside Docker at `/workspace/project/` |
