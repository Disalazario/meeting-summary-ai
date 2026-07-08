# Meeting Summary AI — Prompt Evaluation

Automated evaluation of LLM prompts used in Meeting Summary AI using [promptfoo](https://www.promptfoo.dev/).

## What is evaluated

Three prompt pipelines are tested against sample meeting transcripts, each in its own config file:

| Config file | Prompt | What it does | Key checks |
|------------|--------|-------------|------------|
| `promptfooconfig.yaml` | **summary** | Generates meeting summary (brief, summary, key_decisions) | Valid JSON, required keys present, content quality via LLM rubric |
| `promptfoo.tasks.yaml` | **tasks** | Extracts actionable tasks (description, assignee, deadline) | Valid JSON, tasks array present, deadlines extracted, content quality |
| `promptfoo.topics.yaml` | **topics** | Identifies 3-7 key meeting topics | Valid JSON, topics array with correct count |

## Prerequisites

- **Ollama** running locally with `qwen2.5:7b` model:
  ```bash
  ollama serve
  ollama pull qwen2.5:7b
  ```
- **Node.js** with promptfoo installed (from project root):
  ```bash
  npm install promptfoo
  ```

## Running evaluations

### Quick start — run all evals
```bash
cd evals
./run_eval.sh
```

### Run a specific prompt eval
```bash
./run_eval.sh summary   # only summary prompt
./run_eval.sh tasks      # only tasks prompt
./run_eval.sh topics     # only topics prompt
```

### Manual commands
```bash
cd evals
export OPENAI_API_KEY=dummy  # required by promptfoo even for Ollama

# Run a specific config
npx promptfoo eval -c promptfooconfig.yaml
npx promptfoo eval -c promptfoo.tasks.yaml
npx promptfoo eval -c promptfoo.topics.yaml

# View results in browser
npx promptfoo view
```

## Test fixtures

Sample transcripts in `fixtures/`:

- `transcript_sample_1.txt` — Software project status meeting (10 speakers, ~25 lines). Covers backend integration, frontend dashboard, critical auth bug, deployment, demo preparation.
- `transcript_sample_2.txt` — Budget planning meeting (3 speakers, ~14 lines). Covers Q2 budget allocation, marketing spend, contract approval, training budget.

## Adding new test cases

1. Add transcript files to `fixtures/`
2. Add test entries in the relevant config file under `tests:`
3. Use `file://fixtures/your_file.txt` to reference transcript files
4. Assertion types available:
   - `is-json` — validates output is valid JSON
   - `javascript` — custom JS checks on the parsed output structure
   - `llm-rubric` — LLM-graded content quality (uses Ollama locally)

## Notes

- The `llm-rubric` assertions use the same local Ollama model (qwen2.5:7b) for grading. For more reliable grading, set `OPENAI_API_KEY` to a real key and remove the `defaultTest.options.provider` block from the config files.
- The `OPENAI_API_KEY=dummy` env var is required by promptfoo even when using only Ollama providers.
