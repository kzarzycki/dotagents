---
name: minecraft-building
description: "Use when building structures in Minecraft through the mc-mod MCP (execute_commands, take_screenshot, get_player_info) — houses, castles, matching a reference photo, or any build the user wants to look good. Covers the build→screenshot→critique loop, roof/facade techniques, camera math, and setup gotchas."
---

# Minecraft building via mc-mod MCP

Build in phases and LOOK at each phase before continuing. The mc-mod tools let you place blocks (`execute_commands`) AND see the real client renderer (`take_screenshot`) — use both every phase. One-shotting a build produces ziggurat roofs and dark facades; iterating fixes them.

## Workflow (do not skip)

1. `get_player_info` → absolute coords. Anchor the whole build off these.
2. Build in phases: **site-prep → shell → roof → details → landscaping**.
3. After EACH phase: `take_screenshot` from a hero angle, critique against the target, fix before moving on.
4. Iterate. The first version of a roof/facade is almost never right.

## Screenshots & camera math

`take_screenshot` with x/y/z/yaw/pitch **teleports the single shared player** and points the camera. There is one player — building and viewing share it.

- Set `time set day` + `weather clear` first, or shots come out dark.
- **Hero angle beats dead-on:** pull back ~20 blocks, elevate ~5-8, pitch down slightly, 3/4 view. Reveals depth and matches reference-photo composition.
- **Yaw convention:** look vector `(x,z) = (-sinθ, cosθ)`. `0`=south(+Z), `90`=west(-X), `180`=north(-Z), `-90`/`270`=east(+X). To aim at a target from the camera: `yaw ≈ atan2(-dx, dz)` where dx,dz = target − camera. Getting this backwards points you at empty landscape — verify the first shot shows the build.

## Roofs — the #1 thing that looks bad

Build pitched/gable roofs as a **thin stair shell**, never solid stepped concrete (that's a ziggurat).

- West/left slope: `smooth_quartz_stairs[facing=east]`; east/right slope: `[facing=west]`. Both lean toward the ridge → `/\`. Ridge = full block.
- **Colored concrete has NO stairs variant.** Use `smooth_quartz` (white metal look), `stone`/`andesite`/`brick` stairs for slopes.

## Facade & porch

- Porch posts: slender, widely spaced. **Never put a post directly in front of a window** — it merges into a dark wall and hides the facade.
- Porch roof: thin (bottom-slab), not full blocks.
- Warmth & detail: hanging lanterns (`lantern[hanging=true]`), `spruce_trapdoor[open=true]` as flush shutters, `spruce_fence` railings, `stone_bricks` foundation band + `stone_brick_stairs` stoop, `allium` (lavender look) flower beds, `oak_leaves` shrubs.

## Command order & batching

- **Fills overwrite.** Place windows/doors/details AFTER the surrounding wall/roof fills, or they get buried.
- `execute_commands` takes an array run in order — batch a phase together.
- **Check each command's `status`.** A rejected block-type (`rejected_by_game`, e.g. bad blockstate) fails silently inside an otherwise-successful batch. `light_gray_stairs` = "Unknown block type" is this trap.

## Blockstate syntax reference

- doors: two setblocks (lower + upper half) with `facing`/`hinge`
- stairs: `[facing=,half=,shape=]`
- slabs: `[type=top|bottom|double]`
- logs: `[axis=x|y|z]`
- trapdoors: `[facing=,half=,open=]`
- lanterns: `[hanging=true|false]`

## Setup gotchas

- Fabric loads mods only at JVM start — **relaunch the client after adding jars**.
- A newly-registered MCP server needs a session `/reload` (or `/reload-plugins`) before its tools appear.
- Screenshots need the **GUI client running** with F3+P off (don't pause on lost focus) and "Allow Commands" on. **Dedicated-server mode has no render context — screenshots are disabled there.** Use the single-player / integrated client.
