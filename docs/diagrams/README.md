# Diagrams

The two diagrams in the main README are kept as Mermaid text (`*.mmd`) and drawn to pictures with
[Pele](https://pele.run), a small Mermaid renderer. Each diagram has a light and a dark picture, and GitHub shows the one
that matches the reader's theme.

To change a diagram:

1. Edit the `.mmd` file. Avoid semicolons and hash signs, which Mermaid reads as syntax.
2. Redraw the pictures (needs Node 18 or newer):

   ```bash
   cd docs/diagrams
   npm ci
   npm run render
   ```

3. Open the new `.svg` files and look at them, in light and dark.
4. Commit the `.mmd` and the four `.svg` files together.

A test fails if a picture is older than its `.mmd`, so a forgotten redraw is caught. Pele is a development tool only:
nothing from it ships in the plugin.
