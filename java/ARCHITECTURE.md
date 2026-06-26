# Blockforge Java Architecture

## Current roles

- `Main.java`: application entry point
- `GamePanel.java`: input, game loop, player physics, and interaction orchestration
- `World.java`: voxel storage, terrain generation, and block queries
- `Player.java`: player state
- `IsometricWorldRenderer.java`: superior/isometric rendering
- `FirstPersonWorldRenderer.java`: first-person rendering and targeting
- `ViewMode.java`, `SelectionTarget.java`, `CellProjection.java`: shared model types

## Current model

- the world is now block-based, not column-based
- every `(x, y, z)` cell can contain its own `BlockType`
- mining removes one block
- placement fills one empty voxel adjacent to the selected block
- both cameras render the same voxel world

## Direction

Next structural steps:

1. move world generation out of `World`
2. extract player physics/controller from `GamePanel`
3. add chunk boundaries and save/load
4. separate UI/HUD drawing from gameplay orchestration
