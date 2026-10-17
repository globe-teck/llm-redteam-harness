# Datasets

All loaders download from public sources only, cache under `~/.cache/llm-redteam-harness`
(override with `HARNESS_DATA_CACHE`), and record the sha256 of the exact file used.
No dataset files are committed to this repo; `tests/fixtures/` holds tiny hand-written stand-ins.

| Name | Status | Source |
|---|---|---|
| HarmBench (text behaviors) | loader | github.com/centerforaisafety/HarmBench `harmbench_behaviors_text_all.csv` |
| XSTest | loader | github.com/paul-rottger/exaggerated-safety `xstest_prompts.csv` |
| TruthfulQA | loader | github.com/sylinrl/TruthfulQA `TruthfulQA.csv` |
| SimpleQA | loader | openaipublic.blob.core.windows.net/simple-evals `simple_qa_test_set.csv` |
| InjecAgent (direct-harm, base) | loader (prompts + metadata only, no tool emulation) | github.com/uiuc-kang-lab/InjecAgent `data/test_cases_dh_base.json` |
| AgentHarm | **gated**: parser for a local file you downloaded after accepting the HF terms | huggingface.co/datasets/ai-safety-institute/AgentHarm |
| AgentDojo | **stub**: tasks are Python objects in the `agentdojo` package; bridge not implemented | github.com/ethz-spylab/agentdojo |
| tau-bench | **stub**: needs its simulated user and DB; bridge not implemented | github.com/sierra-research/tau-bench |

## Mandatory CBRN / WMD filter
`load_benchmark()` always runs `harness.datasets.filter.apply_safety_filter`. Items are dropped if
their category matches chemical/biological/radiological/nuclear/WMD/explosive labels, **or** their
prompt text matches a CBRN keyword list (this catches mislabelled items). The filter is not
configurable from the CLI. Dropped ids are recorded in the run manifest. On the public HarmBench
text set at the time of writing, 58 of 400 behaviors are dropped.
Over-dropping is acceptable (e.g. a TruthfulQA item filed under a "biology"-like label).
