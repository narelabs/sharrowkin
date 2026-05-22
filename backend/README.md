# Sharrowkin

Sharrowkin is a local-first autonomous developer agent. It reads a workspace, builds an AST-level project summary, recalls prior solutions from RLD and DSM memory, asks Gemini for code patches, applies them locally, runs tests, and retries with test feedback until the task stabilizes.

The project is consolidated under this directory so the production app, research engines, and references live in one clear tree.

## Project layout

```text
sharrowkin/
├── backend/                  # FastAPI API, WebSocket agent loop, Gemini client
├── frontend/                 # Next.js browser UI
├── integrations/
│   ├── lazystandup/          # AST-level standup report generator
│   └── semanticgit/          # s-git semantic AST parser and VCS engine
├── memory/
│   ├── dsm/                  # Dynamic Segmented Memory
│   └── rld/                  # Recursive Latent DNA
├── cognition/fieldscript/    # FieldScript cognitive-cycle prototype
├── prototypes/desktop/       # Tkinter reference prototype
└── docs/                     # Original task/specification notes
```

## Backend

```bash
cd avos
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
export GEMINI_API_KEY="your-key"
python -m uvicorn backend.main:app --reload
```

API endpoints:

- `GET /api/health` — backend status and cognitive phases
- `POST /api/chat` — real-time 256-dimensional NARE-Field Cognitive Cycle (Observe → Reason → Recall → Stabilize → Commit)
- `POST /api/terminal` — terminal executable proxy that bridges the frontend terminal to Python and DSM commands
- `GET /api/stats` — live system metrics (CPU, Memory, Active Routines) for the premium dashboard
- `POST /api/standup` — LazyStandup report generation with s-git history fallback
- `POST /api/patch/accept` — record accepted patch decisions
- `POST /api/patch/reject` — record rejected patch decisions
- `WS /ws/agent` — streamed Observe → Recall → Reason → Stabilize → Commit events for the autonomous agent

## Frontend

The premium, minimalist Next.js frontend is located in `/shrrowkincleanui` (outside the backend package to maintain pure separation).

```bash
cd shrrowkincleanui
npm install
npm.cmd run dev
```

Open the UI at `http://localhost:3001` (if port 3000 is occupied). The frontend automatically reads data from `http://127.0.0.1:8000`.

## Memory and learning

Runtime memory is stored inside the target workspace under `.sharrowkin/`:

- `rld_genes.json` stores successful reasoning genes.
- `dsm_memory.json` stores project knowledge and solution context.

The agent calls RLD before generation and records successful solutions after stable tests. DSM stores workspace architecture summaries and task outcomes.

## Design rules

The UI uses a clean, high-end Apple-style light panels treatment with Inter font weights and absolute focus on developer efficiency. Zero glow-heavy treatment. Fully native.
