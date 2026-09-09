# Role split with the skill governor

The workflow controller owns the project. It turns the user's goal into a
contract, execution plan and detailed steps, then runs and verifies those steps.

For each step it sends the skill governor:

- the output to produce;
- current inputs and their versions;
- target tool or runtime;
- constraints and acceptance evidence;
- whether the step is creative work, validation or execution.

The governor returns:

- one primary Skill;
- optional complementary Skills with separate duties;
- why competing candidates were excluded;
- boundary and missing-input notes.

The workflow controller writes that decision into the plan, reads the selected
Skill, executes the step and owns the result. A request to update, install,
merge, compare or retire Skills goes back to the governor. AI video is a domain
pack inside this project workflow, not a second project manager.
