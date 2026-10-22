# Third-party notices

## bpmn-js viewer

- File: `src/bpmn_mcp/engine/assets/bpmn-viewer.development.js`
- Project: bpmn-js (bpmn-viewer v17.11.1), https://github.com/bpmn-io/bpmn-js
- Copyright (c) 2014-present, Camunda Services GmbH
- Licence: the bpmn.io licence, https://bpmn.io/license

The file is included unmodified, with its original copyright and licence header. The licence permits use, copying,
distribution and sublicensing, free of charge, on two conditions that apply here:

1. The copyright notice and permission notice stay with every copy. They are in the header of the file.
2. The code that shows the bpmn.io watermark must not be removed or changed, and the watermark must stay fully
   visible wherever the viewer is shown. This plugin uses the viewer only to check that a generated `.bpmn` file loads
   and to write a preview image (`*.camunda-preview.png`). That preview shows the watermark and must not be edited to
   hide it. The SVG, PNG and `.bpmn` files the plugin produces do not contain the viewer.

This summary is not legal advice. Read the full licence at the address above.

## Pele (development tool only)

- Project: Pele, https://github.com/obsidianmd/pele (npm package `pele`, version 1.8.0, pinned in
  `docs/diagrams/package.json`)
- Licence: MIT
- Use: draws the diagrams in `docs/diagrams/` from Mermaid text. The pictures are generated markup. No Pele code is
  included in the plugin or in the repository, and users never run it.
