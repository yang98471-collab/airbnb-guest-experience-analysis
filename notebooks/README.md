# Airbnb Review Extraction Project

## Project purpose

This project prepares Airbnb review data, creates a stratified sample of 50,000 comments, tests a structured extraction method, and runs the final extraction with the OpenAI API.

The README is documentation only. It does not run code or change the analysis.

## Notebook workflow

Run the notebooks in numerical order from the `python2` project folder.

| Step | Notebook | Purpose |
|---|---|---|
| 1 | `01_prepare_data.ipynb` | Clean the raw review file, retain reviews from 2023–2025, and create the basic-clean dataset. |
| 2 | `02_sampling.ipynb` | Create the stratified 50,000-comment sample, lightly clean comments, and create the 24- and 120-comment test samples. |
| 3 | `03_extraction_test.ipynb` | Test and compare the extraction prompt and schema on small samples. Some cells make paid API requests. |
| 4 | `04_full_extraction.ipynb` | Run and audit five resumable 10,000-comment parts, then merge and validate all 50,000 comments. |

`extraction_config.py` is the shared source of truth for the extraction schema, taxonomy, scoring rules, and prompt. Do not change it in the middle of an extraction run.

## Important operating instructions

1. Open `python2` as the VS Code project folder.
2. Confirm that `Path.cwd()` points to the `python2` folder before running a notebook.
3. Run notebooks 1–4 in order when rebuilding the project from the raw data.
4. Read cells marked **PAID API CELL** before running them.
5. Do not use **Run All** in notebook 3 unless you intentionally want to send every paid test request.
6. Never type an API key directly into a saved notebook. Use the hidden `getpass` prompt or an environment variable.
7. Keep only one final extraction process running at a time.
8. Do not change the model, prompt, schema, batch size, reasoning setting, partition files, or partition boundaries during the final 50,000-comment run.

## Project layout

```text
python2/
|-- 01_prepare_data.ipynb
|-- 02_sampling.ipynb
|-- 03_extraction_test.ipynb
|-- 04_full_extraction.ipynb
|-- extraction_config.py
|-- README.md
|-- src/
|   `-- final_extraction_workflow.py  # Partition, shared-budget, and merge safeguards
|-- data/
|   |-- raw/          # Original source data
|   |-- processed/    # Cleaned intermediate datasets
|   |-- samples/      # 50,000-, 120-, and 24-comment samples
|   `-- final_parts/  # Five frozen 10,000-comment production inputs
`-- outputs/
    |-- extractions/  # Test results, errors, and usage records
    |-- comparisons/  # Prompt/model comparison tables
    `-- final_50000/  # part_01 ... part_05 checkpoints plus merged outputs
```

## Data flow

| Stage | Input | Main output |
|---|---|---|
| Raw preparation | `data/raw/reviews_full.csv` | `data/processed/reviews_2023_2025_basic_clean.csv` |
| Sampling | Basic-clean dataset | `data/samples/reviews_sample_50000_extraction_ready.csv` |
| Extraction testing | 24- and 120-comment samples | `outputs/extractions/` and `outputs/comparisons/` |
| Final extraction | Five frozen 10,000-comment parts | `outputs/final_50000/part_01/` through `part_05/`, then `merged/` |

## Running the five production parts

Run only one part at a time:

1. Open `04_full_extraction.ipynb` and set `PART_NUMBER` to `1`, `2`, `3`, `4`, or `5`.
2. Restart the notebook kernel, then run the cells from the top in order.
3. At the paid-run prompt, type `RUN PART 1`, `RUN PART 2`, and so on for the selected part.
4. After the paid cell finishes, run the audit cell for that part.
5. Repeat for the remaining parts. After all five audits pass, the audit cell automatically creates and validates the merged 50,000-comment outputs.

Each part has independent checkpoints. The $80 safety limit is shared across all five parts and is checked before every 10-request wave.

## Python requirements

The notebooks use these main packages:

- `pandas`
- `numpy`
- `matplotlib`
- `pydantic`
- `openai`
- Jupyter support in VS Code

## Final 50,000-comment checklist

Complete these checks before entering the final production confirmation:

- [ ] The notebook is running from the `python2` project folder.
- [x] Completion status is assigned from saved records and the final audit; missing or invalid comments report `incomplete`.
- [x] API retries use three total attempts, selective retry rules, `Retry-After`, exponential backoff, and random jitter.
- [x] Resuming validates the manifest, complete run signature, input mapping, saved schemas, result/usage pairing, and duplicate or unexpected IDs before skipping any comments.
- [x] The shared $80 cost limit is checked before each new 10-request wave across all five parts.
- [x] The 50,000-row master input and five non-overlapping 10,000-row parts pass validation.
- [ ] No other final extraction process is running.
- [ ] The final audit reports `completed`, with zero missing comments, unexpected IDs, schema errors, and evidence-quote errors.

## Extracted field reference

| Field | Meaning |
|---|---|
| `comment_id` | Identifies the source review. |
| `aspect` | Identifies the business dimension being discussed. |
| `object` | Identifies the specific entity or feature. |
| `observation` | Summarizes what happened or what the guest experienced. |
| `finding_category` | Classifies the finding as a strength, problem, or neutral observation. |
| `aspect_score` | Measures how positive or negative the finding is. |
| `severity_score` | Measures the seriousness of a negative impact. |
| `evidence_quote` | Preserves the exact review text supporting the finding. |

## Quietness scoring reference

| Score | Meaning |
|---:|---|
| +5 | Exceptionally quiet; an explicit major benefit such as perfect sleep. |
| +4 | Very or extremely quiet. |
| +3 | Clearly quiet. |
| +2 | Mostly quiet. |
| +1 | Slightly or reasonably quiet. |
| 0 | No clear evaluation or balanced/mixed evidence. |
| −1 | Slightly noisy. |
| −2 | Noticeable but manageable noise. |
| −3 | Clearly noisy. |
| −4 | Very or extremely noisy. |
| −5 | Unbearable noise or noise that prevented sleeping or staying. |

## 24-comment test allocation

| Year | Listing activity | First allocation | Proportional extras | Final |
|---:|---|---:|---:|---:|
| 2023 | Low | 1 | 0 | 1 |
| 2023 | Medium | 1 | 0 | 1 |
| 2023 | High | 1 | 1 | 2 |
| 2023 | Very high | 1 | 3 | 4 |
| 2024 | Low | 1 | 0 | 1 |
| 2024 | Medium | 1 | 0 | 1 |
| 2024 | High | 1 | 1 | 2 |
| 2024 | Very high | 1 | 3 | 4 |
| 2025 | Low | 1 | 0 | 1 |
| 2025 | Medium | 1 | 0 | 1 |
| 2025 | High | 1 | 1 | 2 |
| 2025 | Very high | 1 | 3 | 4 |
| **Total** |  | **12** | **12** | **24** |

## Viewing this README

In VS Code, press `Ctrl+Shift+V` while this file is open to display the formatted Markdown preview.
