# Versioned application skills

These files hold the application's existing prompts and verification notes as
read-only package assets loaded by `code_agent.skillbook`. Execution remains in
Agent/Gateway, output schemas in the Pydantic models, and validation in
CatalogSafety. The assets add no agents, tools, provider selection, registration
authority, candidate filtering, or question-specific answers.

Each JSON manifest contains exactly `id`, `version`, `instruction_file`, and
`instruction_sha256`. The loader checks the supported identity, version format,
local Markdown path, nonempty instructions, and checksum, then returns an
immutable value. Duplicate or unexpected manifest keys fail validation. Schemas,
execution steps, and safety policies are not duplicated in the manifests.

| Skill | Runtime entry | Output |
| --- | --- | --- |
| `plan` | Agent's existing intent planning | `Plan` |
| `search_explanation` | Explanation after snapshot-validated retrieval | `Explanation` |
| `compare` | Explanation with existing deterministic rule comparisons | `Explanation` |
| `draft` | Authorized unregistered wording, followed by retrieval/comparison | `Wording` |
| `verification` | Existing `CatalogSafety.validate` procedure | `None` on success; `DomainError` on failure |

The table describes the owning runtime handlers, not manifest-enforced steps.
Comparison shares `search_explanation.md` and receives the existing deterministic
rule comparison facts. Verification documents the existing checks; its Markdown
does not replace a judge prompt. Independent faithfulness and grounding results
remain the responsibility of CatalogSafety.

## Runtime connection

`agent.py` loads its three existing prompt constants through `instructions(id)`.
`skill_for_schema(schema, payload)` selects plan/draft/explanation and selects
comparison when `rule_comparison` is nonempty. Gateway uses that selection to
identify the prompt in telemetry while retaining its existing provider call and
Pydantic validation. An empty comparison payload selects `search_explanation`.

CatalogSafety loads `verification` to identify its validation procedure. Its
existing code performs registered-field binding, numeric, faithfulness, and
grounding checks. Explicit registered-field quotations must match the cited
code's original field. A valid manifest or recorded skill identity does not prove
that these checks passed; runtime results and focused tests provide that evidence.

PII masking and input defenses run on the original evidence structure before
`encode_evidence`. The encoder only changes the model transport representation.
Keep the original, masked structure for deterministic checks and DB originals
for returned candidates. Decode with `decode_evidence` where an adapter requires
the original structure. Never treat table keys, row positions, or envelope text
as additional registered evidence.

The retrieval path is independent of these prompt assets. Catalog search uses
the pinned upstream hybrid flow, and its reranker adapter forwards original
indexed chunks without field reconstruction, an extra candidate cap, or text
windows. See the
[implementation and evaluation record](../../../docs/CATALOG_SKILLS_2026-09-22.md)
for the upstream candidate limit, original 512-character cutoff, build-time
raw-logit correction and batch size 4, CPU scheduling, and pending final after run.

For a deliberate instruction change, update the Markdown, its SHA-256, manifest
version, and focused tests together. Changes to execution, schemas, or safety
belong in their owning runtime modules and tests. Do not add question-to-code
mappings. Compare provider token usage and answer validity on fixed synthetic
scenarios before claiming an improvement.
