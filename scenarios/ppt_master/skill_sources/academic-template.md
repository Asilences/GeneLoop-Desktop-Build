# Academic template reuse — GeneLoop adaptation

Source: Academic PPT Master, commit 6825d33f2931b8894435b9bd25c08cfce3476ff0.
This is a rewritten reference, not a second Agent or an executable recipe.

When an editable template is supplied, first identify its actual slide objects,
page size and content roles. Keep a native PPTX template on the native editing
route; do not convert it to SVG merely to fit the default renderer. An SVG
template can remain on the existing SVG authoring/export route. Never silently
substitute one route for the other.

Map current content to the chosen template once. Preserve the template's visual
structure, edit only requested fields, and write a new output. Template example
numbers, references and branding are not facts for the current task. Keep unused
pages and their notes unchanged during a local revision. If content does not fit,
report the affected field and shorten or select another layout; do not shrink
every page or rebuild the deck.

Use read_ppt_design for the available design/parameter contracts. For supported
native layouts use compose_ppt_page; certified parameterized pages use
create_ppt_page. Preserve a successful page and its current SHA during revision.
Use finalize_ppt for the selected authoring route's supported editable export,
then inspect its actual previews; read_image is needed only for unseen images.
Native PPTX template filling is a separate capability, not implied by these
SVG page tools. Retain evidence of unsupported requests rather than claiming
template fidelity without checking the resulting file.

Adaptation: retain template/object preservation and source separation. Replace
upstream stage/checkpoint requirements with GeneLoop task handling. Do not add
audio/video stages, forced branding, repeated environment checks or an extra
export pipeline. Candidate order/bindings must be learned from real execution.
