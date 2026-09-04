# Recorded walkthrough script

Target length: 3–5 minutes.

## 0:00–0:30 — Introduce the project

“This is a bounded tool using research agent. The model can choose between web search, page fetching, evidence summarisation, and final answer submission. The controller will not display a factual claim unless its source was fetched and its supporting quotation exists in the fetched text.”

Show the architecture diagram near the top of `README.md`.

## 0:30–1:15 — Show the tools

Open `src/research_agent/schemas.py` and name the four tools:

1. `search_web`
2. `fetch_page`
3. `summarize_sources`
4. `submit_answer`

Open `src/research_agent/tools.py`. Briefly show that search results register candidate URLs but do not receive source IDs. Point out that `fetch_page` creates `S1`, `S2`, and so on only after a successful fetch.

## 1:15–2:00 — Demonstrate a run

For a live run:

```bash
research_agent "What are the benefits and limitations of heat pumps?" --trace
```

If API access is unavailable, use the deterministic demonstration:

```bash
python -m research_agent.demo
```

In the output, point out:

- the model/tool sequence;
- how many of the eight steps were used;
- source IDs beside every claim;
- the exact evidence passage displayed below each claim;
- clickable source URLs.

## 2:00–2:35 — Demonstrate failure recovery

Open `examples/run_3_failure_recovery.md`.

Explain that the first page fetch returns a structured timeout rather than throwing an uncaught exception. The agent tries an alternative search and, because no reliable evidence is found, submits no factual claim and clearly reports the limitation.

## 2:35–3:15 — Show the hard stop

Open `src/research_agent/agent.py` and show the `for` loop over `max_steps`.

Point out:

- `parallel_tool_calls=False`;
- the final round `tool_choice` forcing `submit_answer`;
- the fallback `Research incomplete` result when no valid submission exists.

Then mention that the step limit test intentionally uses a fake model that requests search forever.

## 3:15–4:00 — Show citation validation

In `src/research_agent/tools.py`, show `submit_answer` checking:

- every claim has evidence;
- every source ID exists in the fetched source ledger;
- each quotation is at least 20 characters;
- each normalized quotation appears in the actual fetched page text.

Explain that an invalid submission becomes a tool error, allowing the model to repair it while steps remain.

## 4:00–4:30 — Run tests

```bash
python -m unittest discover -s tests -v
python -m compileall -q src tests
```

End by showing the three example run links in the README.
