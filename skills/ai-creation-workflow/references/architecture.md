# Architecture

The system has two top-level roles and two supporting layers.

1. **Skill manager:** `skill-governor` discovers capabilities, allocates a
   suitable skill to a requested stage, tracks source and quality evidence,
   reviews overlaps, and performs reversible updates.
2. **Workflow controller:** `ai-creation-workflow` owns the project contract,
   execution plan, detailed steps, dependencies, decisions, gates, progress,
   validation and delivery. It asks the skill manager for assignments and then
   carries those assignments through the project.
3. **Craft:** installed specialist skills create scripts, shot plans, prompts,
   visual effects, sound and other domain artifacts.
4. **Execution:** runtime routers and backend adapters submit approved work,
   monitor it, download results and preserve external IDs.

The workflow controller routes each stage through the skill manager rather than
choosing by filesystem keyword. One stage gets one primary skill. Complementary
skills must have a separate output or validation duty; two skills must not
silently rewrite the same artifact.
