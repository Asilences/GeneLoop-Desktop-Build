---
name: ppt-master
description: Create and revise editable PowerPoint presentations from a topic, conversation, documents, images or an existing deck using GeneLoop's integrated presentation tools.
---

# GeneLoop Presentations

Use the user's audience, purpose, content, template and visual preferences to plan the presentation. A topic and desired outcome are sufficient to start. Choose reasonable defaults for unspecified presentation details and state significant assumptions at delivery. Ask together for missing facts that determine the content.

Use `read_ppt_design` to browse compact theme cards or inspect a theme or certified component contract. Select a suitable design once. `start_ppt` creates an editable project with its theme, typography and layout defaults. User templates and existing decks follow the original-PPTX route below.

Write the content outline into `design_spec.md`, then call `prepare_ppt(project)` for actual regular/bold font measurements. Compose SVG pages in the returned project directory. Reuse an applicable certified page with `create_ppt_page`, supplying current content parameters and a page filename. The host installs the page and records its version. Write speaker notes under `notes/`.

Use `compose_ppt_page` for ordinary covers, sections, bullet pages, two-column comparisons, image/text pages, bar charts and closing pages. Supply current content and notes. The host measures text with the installed font and rejects capacity overflow. This shared foundation is available in both comparison modes. For a supplied template or more detailed visual choices, read `design-conventions.md` through `read_ppt_design`.

For a simple labelled numerical bar chart, use the built-in `bar_chart` layout with the current source values. It computes a common baseline, bar heights and tick positions together. Do not independently hand-code those three quantities. For unsupported charts, use one shared numerical scale function and verify ticks and bars against that function. A visually tidy chart with inconsistent scales fails factual acceptance.

Call `finalize_ppt(project)` for font and format checks, editable PPTX export, Office PDF and page PNGs. Read the returned Office images to assess visible content and layout. Repair concrete findings on the affected pages. Reuse unchanged checks. Present the current PPTX and requested companion files through `present`.

The host handles font resolution, calibration, file installation, export and mechanical diagnostics. Content interpretation, visual communication and factual accuracy remain model decisions. Treat warnings according to their visible effect and the user's requirements. A stalled repair requires a different effective method or the ordinary authoring fallback.

When the user has authorized autonomous completion, continue a reversible layout repair within that task. Ask for missing scientific facts or a consequential user preference when needed. Choose ordinary technical recovery steps such as correcting paragraph placement directly.

Use the prepared role rates for manual SVG text placement. If text is too dense, shorten it or choose another page structure. Direct text_measure imports, module inspection, per-string font experiments and repeated font diagnostics duplicate the host work. Reference documents provide drawing syntax and design examples. Their older operational calibration or export instructions are superseded by prepare_ppt and finalize_ppt.

## References for specific work

The integrated engine uses the pinned modules under `/opt/geneloop/ppt-master`. Read only the reference required by the current operation.

- For native SVG shape, table, chart and formula authoring, inspect the relevant section of `references/executor-base.md` and the helper's documented interface.
- For a user-supplied PPTX template or editing an existing deck, read `workflows/edit-native-pptx.md`. Import into a new project with `scripts/pptx_to_svg.py --roundtrip`, preserve the selected native structures and use that route's export. Treat the input file as immutable.
- For a reusable template workspace, read `workflows/create-template.md` when needed.
- For original document conversion, use the source tools and the pinned converter. Source figures, numbers and citations retain their provenance.

GeneLoop owns the task lifecycle, execution permissions, review policy and recovery. Optional design review is a separately metered background activity. Record source-supported facts and clearly label illustrative data or proposed plans.
