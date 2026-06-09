# AstroTalk Content Safety Detection Workbench

A content safety detection and review pipeline for the AstroTalk astrology platform. The system analyses consultant-user chat sessions to detect NSFW, harmful, or policy-violating content, aggregates risk signals across multiple LLM classifiers, and exposes a human-review interface for auditors.

---

## Project Structure

```
astrotalk-engine/
├── engine/                   # Core detection logic
│   ├── aggregator.py         # Merges signals from multiple classifiers
│   ├── chunker.py            # Splits sessions into analysable chunks
│   ├── classifier.py         # LLM-backed classification calls
│   ├── consultant_analyser.py
│   ├── data_loader.py
│   ├── intent_library.py
│   └── language_detector.py
├── pipeline/                 # Batch orchestration
├── store/                    # Persistence layer (SQLite / file store)
├── review_interface/
│   ├── api/                  # FastAPI backend for the review UI
│   └── frontend/src/         # React / Next.js review dashboard
├── export/                   # Report and export utilities
├── validation/               # Ground-truth evaluation and metrics
├── data/
│   ├── raw/                  # (git-ignored) source data from AstroTalk
│   ├── processed/            # (git-ignored) intermediate pipeline outputs
│   ├── ground_truth/         # (git-ignored) labelled evaluation sets
│   └── samples/              # (git-ignored) anonymised sample sessions
├── reports/
│   └── pilot_report.py
├── main.py
├── config.py
├── requirements.txt
├── .env.example
└── README.md
```

---

## Setup

### 1. Clone and create a virtual environment

```bash
git clone <repo-url>
cd astrotalk-engine

python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in the required values:

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | API key for Claude (Anthropic) |
| `GEMINI_API_KEY` | API key for Google Gemini |
| `GROQ_API_KEY` | API key for Groq inference |
| `DB_PATH` | Path to the SQLite database (e.g. `store/astrotalk.db`) |
| `LOG_LEVEL` | Logging verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR` |

---

## Running the Batch Pipeline

The batch pipeline reads raw session data, runs the detection engine across all chunks, and writes results to the store.

```bash
python main.py
```

To target a specific input file or override config at runtime, pass arguments as defined in `config.py`.

---

## Starting the Review Interface

The review interface consists of a FastAPI backend and a frontend dashboard.

### API backend

```bash
cd review_interface/api
uvicorn main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### Frontend dashboard

```bash
cd review_interface/frontend
npm install
npm run dev
```

The dashboard will be available at `http://localhost:3000`.

---

## Running Validation

To evaluate classifier performance against the ground-truth labelled dataset:

```bash
python -m validation.evaluate
```

This produces precision, recall, and F1 scores per category and writes a summary to `reports/`.

---

## Notes

- Raw data, processed outputs, and ground-truth files are **git-ignored** — never commit session data.
- All LLM calls are routed through `engine/classifier.py`; swap models by changing `config.py`.
- The aggregator in `engine/aggregator.py` combines multi-model signals into a single risk score.
