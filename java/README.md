# Blockforge Java Port

This is the first Java foundation for the project.

What it includes:

- Java 21
- no external libraries
- Swing window with a small game loop
- generated voxel terrain rendered in two views
- superior/isometric camera
- first-person camera on the same world state
- player movement, jump, gravity
- cylindrical player-footprint collision for grounded support and falling
- horizontal edge depenetration and nearest-free recovery while falling
- mouse-based block selection
- block mining and placement
- hotbar with 5 block types
- void pits
- death and automatic respawn when you fall into the void
- per-block editing: stacked blocks are independent voxels
- pause menu
- local save/load of world edits, player position, camera, hotbar and deaths
- chunk-based world traversal
- conservative first-person chunk culling before mesh rendering
- greedy meshing for first-person exposed voxel surfaces
- lightweight ambient occlusion on greedy top surfaces
- first-person greedy meshing for exposed side and bottom surfaces
- dirty chunk mesh cache invalidated by block edits and save-load changes
- per-face distance/cone culling before Java2D projection

## Build

From the project root:

```powershell
javac -d java/out java/src/blockforge/*.java
```

## Run

```powershell
java -cp java/out blockforge.Main
```

Oppure direttamente:

```powershell
.\run-java.ps1
```

## Controls

- `W A S D` move
- `Space` jump
- `V` or `F5` switch between superior and first-person view
- `Q / E` rotate the camera
- `Mouse move` look around in first-person
- `Up / Down` look up and down in first-person
- `Left click` mine the selected block
- `Right click` place one block next to the selected block
- `1-5` change selected block
- `R` respawn manually
- `Esc` or `P` pause/resume
- `S` save from the pause menu
- `L` load from the pause menu
- `F6` quick-save
- `F9` quick-load
- `T` in pause menu toggles auto-step

## Save file

The Java version saves to:

```text
java/save/blockforge.properties
```

## Current limits

- collision now uses a vertical cylinder footprint for the player; falling uses foot-center support and auto-step is optional
- falling lands only on valid ground support; side/corner penetration is resolved horizontally
- movement collision uses the player's physical cylinder, not an enlarged camera volume
- optional auto-step snaps to the real top of the obstacle instead of adding a fixed vertical jump
- corner sliding nudges the player around tight block corners before optional auto-step runs
- save/load currently stores the whole small prototype world, not streaming chunks
- greedy meshing currently powers first-person rendering; the isometric renderer still draws individual block faces
- mesh caching is in-memory only and rebuilt when chunks become dirty
- first-person render distance is intentionally conservative to keep Java2D responsive
- there are no textures yet, only colored block faces
- generated void pits are still the only true "void" zones

This is now a playable Java sandbox base. The next serious step is choosing between:

- chunk saving/loading
- swept collision and smoother edge handling
- textures and chunk meshing

## Architecture

See `java/ARCHITECTURE.md` for the current module split.
