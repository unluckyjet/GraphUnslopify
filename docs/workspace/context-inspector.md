# Select an element to show its settings

In the current-source figure editor, render your figure and choose **Inspect
element** below it. Click a supported axis or uncertainty mark, or use the
**Selected figure element** menu with the keyboard.

- An axis shows that source binding's label,units,scale and limits. A horizontal
  bar chart preserves the source meaning: its horizontal measurement axis edits
  the Y binding,while its vertical category axis edits the X binding.
- An uncertainty mark shows summary and uncertainty controls,including the
  independent observation ID. The policy applies across the figure; inspect the
  displayed scope before changing an estimator or sampling assumption.
- **Whole figure** shows figure wording,style and export controls.
- **All settings** restores the complete form. Advanced JSON remains available.

Selection changes the visible controls without changing your specification or
verification status. Editing uses the existing validation and undo history;
render again to check a change. **Undo change** restores the previous intent,
which can then be rendered and verified normally.

Text editing,findings and element inspection have separate interaction modes.
Entering one hides the other overlays. Existing drafts retain their normal
current-context checks.

## Supported geometry and visible limits

Targets come from the final cropped PNG draw and bind its SHA256,dimensions,
run and canonical-spec identity. An edit,new dataset,provisional preview or
superseded reply cannot reuse an old map. Mismatched images disable inspection.

Supported Cartesian axes carry explicit source bindings. Generated line bands,
line error bars and bar-chart error bars have explicit interval ownership;
ordinary filled areas are not inferred to be uncertainty. Controls apply where
the selected binding/policy is shared. Unsupported secondary axes,unmapped
panels,other marks and custom clipping remain accessible through All settings
or Advanced JSON. Geometry gaps do not change scientific acceptance.

Inspection has bounded target/path capacity. It does not certify experimental
independence,statistical appropriateness or complete readability.

## Inspect a figure in a paper

Choose the current JSON definition and its matching saved run/figure,then select
**Inspect element**. The saved PNG moves beside the original definition controls.
The same axis/interval/whole-figure menu scopes those controls. **All settings**
returns the image to saved history and restores the full form.

These controls edit the original JSON. Manifest data/claim overrides and shared
or selected paper presentation settings retain their own controls and visible
scope. File-backed and inline JSON can be editable; authored Python stays read
only. An older run with different current inputs cannot edit the new definition.

Edit,undo and save through the normal definition workflow,then audit the paper
to check the changed figure. **Regenerate changed figures** can copy intact PNG
geometry with its verified accepted figure; scripts still execute separately.
Selection never changes a failed scientific result into a pass.

Maps require an original recorded PNG and supported saved geometry. Missing old
maps,PDF/SVG-only exports,changed bytes and unsupported targets remain unavailable;
use the normal form or regenerate PNG evidence. The workspace verifies actual
displayed PNG bytes and refuses late responses for another owner or revision.

## Development evidence

Pipeline [91](../../pipeline/done/91-context-inspector.md) records the full
figure/paper requirement. The91a single-figure implementation is accepted at
db73e73 after exact14 CI. Paper91b transport/ownership is accepted at4c0aa91
after exact14 CI. The paper browser control also starts its mapped interval
below the viewport:element-relative pointer input must scroll to the actual
saved geometry and reveal the matching uncertainty controls. Its18 original
ownership,edit/reuse,history,mobile and failed-science assertions remain.
The complete [thirty-idea roadmap](../../pipeline/research-platform-roadmap.md)
remains active. No new comparative speed or scientific-superiority claim is made.
