# AI video domain pack

Use this dependency graph and omit stages that the task does not need:

`brief -> script -> content units -> story shots -> generation segments ->
reference plan -> prompts -> runtime -> render -> media QA -> edit/sound ->
delivery`

Keep three levels distinct:

- **Content unit:** one dramatic or informational beat.
- **Story shot:** the editorial shot design used to tell that beat.
- **Generation segment:** one self-contained model request at a real continuity
  or duration boundary.

A generation segment states its opening state, transition and ending state. Do
not assume a video model remembers an earlier request. An anchor image may lock
blocking, prop position and physical contact while leaving composition, pose,
lighting and effects to the prompt unless those properties are intentionally
locked.

Before H3 execution, require bilingual prompts when the production needs them,
the real upload order, usable reference files, workflow parameters and the
execution gate defined in `gates-and-evidence.md`.

Choose the smallest production path:

- **Single-shot fast path:** when one self-contained segment, approved inputs
  and one deliverable are sufficient, go directly from segment/material check
  to prompt, runtime contract, generation and media validation. Do not create a
  full-project storyboard or load unrelated post-production rules.
- **Project path:** retain the dependency graph for multiple shots, continuity,
  editorial structure, handoffs or resumable production.

Before a batch, identify the segment with the highest identity, motion,
continuity, reference or runtime risk. Generate one representative high-risk
sample first when a failure would propagate across the batch. Its approval is
the batch-expansion gate; a low-risk single shot does not receive this extra
gate.
