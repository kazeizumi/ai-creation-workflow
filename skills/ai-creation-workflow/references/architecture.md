# Architecture

The system has four layers.

1. **Portfolio:** `skill-governor` discovers capabilities, tracks source and
   quality evidence, reviews overlaps, and performs reversible updates.
2. **Control:** `ai-creation-workflow` owns the project contract, stage graph,
   decisions, gates and evidence.
3. **Craft:** installed specialist skills create scripts, shot plans, prompts,
   visual effects, sound and other domain artifacts.
4. **Execution:** runtime routers and backend adapters submit approved work,
   monitor it, download results and preserve external IDs.

The control layer routes by capability rather than filesystem keyword. One
stage gets one primary skill. Complementary skills must have a separate output
or validation duty; two skills must not silently rewrite the same artifact.
