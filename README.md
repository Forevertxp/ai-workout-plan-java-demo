# AI plan boundaries: a standalone Java and data-tool demo

An educational companion to **Building an AI Workout Plan Generator in Java: PDF Data, LoRA, and Output Validation**.

This repository reproduces resource validation, bounded output repair, task identity, stale-result protection, and a proposed review-to-SFT export. All fixtures are synthetic. It contains no member records, book passages, credentials, or private application dependencies.

## Requirements

- JDK 17 or newer (`java` and `javac`).
- Python 3.10 or newer.
- No API key, Redis server, model download, or third-party package is required.

## Run the checks

From the repository root:

```bash
mkdir -p build
javac -d build src/PlanDemo.java
java -cp build PlanDemo
python3 -m unittest -v test_data_tools.py
```

Expected: 15 Java checks and four Python tests pass. An assertion failure or failed test exits unsuccessfully.

Java checks cover trusted names, category membership, units, numeric text, duplicates, repair limits, transport failures, task reuse, stale results, and concurrent submissions. The two async scenarios have different outcomes:

- Same active **plan ID**: reuse the task.
- Clear A, create B, then A returns: compare-and-set rejects A's stale update.

The 16-submission concurrency check uses real Java threads, but only inside one JVM. No network race, Redis failover, persistence, or remote cancellation is tested.

## Audit a message-format dataset

```bash
python3 audit_jsonl.py data/synthetic_messages.jsonl
```

Expected synthetic report: three records, one repeated-question group, two question occurrences beyond the first, and one exact duplicate record. Exact-record deduplication is distinct from repeated-question accounting. Neither is semantic deduplication.

You can audit your own file by passing its path. The tool emits counts, a file hash, and issue line numbers. It does not print question or answer contents. Do not commit real input files to this repository.

## Export synthetic professional reviews into SFT files

```bash
python3 build_dataset.py data/synthetic_reviews.jsonl build-dataset-v1
```

Expected output:

```json
{
  "accepted": 24,
  "skipped": 1,
  "splits": {"train": 20, "validation": 2, "test": 2}
}
```

The exporter requires approval plus the example score threshold, validates target resource membership and units, and partitions by member group. It only projects `generationInput` into the user message. Scores and later outcomes are not silently injected into the earlier model context.

The output directory includes three message-format JSONL files and a separate provenance manifest. Use a new directory for another export; the tool refuses to overwrite a dataset version. The example score threshold of 4/5 and 80/10/10-style group allocation are teaching choices, not validated professional or statistical standards.

This exporter is intentionally small. It does not provide a complete plan schema validator, numerical load limits, near-duplicate detection, consent management, or clinical review. Cases must be reviewed before entering a real training process. In a real service, also group related cases and sources, consider time-based holdout, and define review rubrics.

## Differences from the application

| Topic | Application behavior inspected | This demo |
|---|---|---|
| Model invocation | Spring AI Alibaba agent | Controlled `Supplier<Plan>` test double |
| Plan structure | Nested categories and projects | Compact `choices` list |
| Invalid selected project | Some items are filtered | Entire draft is rejected |
| Task coordination | Redis Lua compares serialized snapshots | `ConcurrentHashMap` compares immutable records |
| Task expiration | Deadline and cache retention | Not implemented |
| Error repair | Appends error summary to original prompt | Supplier returns a controlled second draft |
| Professional review export | Planned feature | Proposed synthetic prototype |

The stricter draft validation intentionally demonstrates an alternative policy. Do not copy it into the application without deciding whether filtering or rejection is appropriate. The demo checks positive numeric amounts; that is not proof of appropriate exercise dosage.

## Optional Redis illustration

The following captures the update condition, but is not executed by the demo:

```lua
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
redis.call('SET', KEYS[1], ARGV[2])
return 1
```

A production implementation must define TTL, initial creation, deletion, access control, retries, and recovery. Compare-and-set protects a result record; it does not ensure exactly-once remote inference.

## What the results mean

Passing these checks demonstrates the specified synthetic software cases. It does not establish an improvement in model accuracy, a successful cloud deployment, or professional suitability of a generated plan.
