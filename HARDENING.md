# Hardened LeLab

This fork of [huggingface/leLab](https://github.com/huggingface/leLab) is for one SO-101 on one laptop.
It changes defaults so that nothing reaches the network or installs code unless you ask.

## Changes

| Area | Upstream | This fork |
| --- | --- | --- |
| Who can call the API | Any website (`allow_origins=["*"]`), any `Host` | LeLab's own pages on `localhost`, `127.0.0.1` or `[::1]`, ports 8000 and 8080 |
| WebSocket `/ws/joint-data` | Any origin | Same origin check as HTTP |
| `?api=` link parameter | Any URL, saved in the browser | Loopback addresses only |
| Self-update | Button installs the latest unpinned commit | Disabled; no GitHub calls |
| In-app package installs | `pip install` from the UI | Disabled; the UI shows the command to run |
| Hugging Face Hub | Online | Offline unless `HF_HUB_OFFLINE=0` |
| Hugging Face telemetry | On when online | Off (`HF_HUB_DISABLE_TELEMETRY=1`) |
| Dataset uploads | Public by default | Private by default |
| LeRobot | `huggingface/lerobot@v0.6.0` with `core_scripts`, `feetech`, `training` | Hardened fork at a pinned commit with `feetech`, `dataset`, `pynput-dep` |
| FastAPI and uvicorn | `fastapi[standard]` | `fastapi`, `uvicorn` |

The dependency change drops packages LeLab does not import:
`fastapi-cloud-cli`, `sentry-sdk`, `agent-detector`, `detect-installer`, `fastar`, `rignore`,
`httpx2`, `httpcore2`, `wandb`, `gitpython`, OpenTelemetry, `rerun-sdk`, `foxglove-sdk`,
`accelerate`, `uvloop`, `httptools`, and `watchfiles`.

`fastapi` itself requires `opentelemetry-api`. Without the OpenTelemetry SDK and an exporter, that package records and sends nothing.

## Install

Pin both the LeLab commit and an upload date. Replace `<commit>` with a reviewed commit of this fork.

```bash
uv venv --python 3.12
source .venv/bin/activate
uv pip install --exclude-newer 2026-10-11T00:00:00Z \
  "lelab @ git+https://github.com/mbattaglia/leLab.git@<commit>"
lelab
```

## Using the Hub on purpose

Download a model yourself, then run LeLab offline:

```bash
HF_HUB_OFFLINE=0 hf download lerobot/<model> --revision <commit>
lelab
```

To upload a dataset or use Hub listings, start LeLab with `HF_HUB_OFFLINE=0 lelab`.

## Optional features

Local training needs `accelerate`. Experiment tracking needs `wandb`.
Install them yourself after reviewing them, with the same `--exclude-newer` date.

## Hosted frontend

The upstream HF Space frontend can call a local backend. This fork blocks that by default.
To allow it, set `LELAB_ALLOWED_ORIGINS=https://lerobot-lelab.hf.space`.
