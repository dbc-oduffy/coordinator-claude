# Design canvas recipe

**Size the design work, not the t-shirt.** A large design ask goes to the Claude Design canvas: produce
or iterate a canvas through the Artifact tool's Design type, then review it. Large means a redesign, a
new screen, several layouts to compare, or a design-system record, at any t-shirt. A small ask (a
`staff-ux` flow review inside a plan, a spot check, one component's tweak) stays with the reviewer agent.
A human designer is a PM-gated exception, named as one (brand sign-off). Offering the PM a "hand it to
the designer yourself" fork for a large ask is the defect. Tripwire: `A-LARGE-DESIGN-ASK-GOES-TO-THE-CANVAS`.

## The repo holds the design; the link is a view

**A link belongs to the login that published it**, and other logins reach it only if its owner shared
it. After a login swap it is out of reach though it still exists, so the repo is the source.

1. **Write the source into the repo first**, under `docs/design/<slug>/project/`, committed in the step
   that produces it. Its `README.md` says the files are canonical, carries steps 2 and 3 as the republish
   recipe, and records the URL as "current published view, <date>, owned by <login>".
2. **Start the canvas:** Artifact `action: "quickstart"`, `intent: "design"` returns the Design type's
   `type_url`; resolve it every time. Publish with that `type_url`, a `title`, no files and
   `auto_open: "after_first_write"`.
3. **Fill it** per the create result, publishing `project/` with `root` set to the design folder.
4. **A link out of reach** (other login, deleted) is republished from the files under the current login.
   Never cite a link as the source of a value.

## Design systems

**A repo with a design system keeps it published as a Design System artifact, so a canvas can attach
it.** Build it from the token CSS and token record at `HEAD`, never from memory or an older artifact.
Publishing is private and EM-autonomous; sharing is the gated act. Republish when the token files change
or the link is out of reach, recording the URL in the design-system README as above. Tripwire:
`A-DESIGN-SYSTEM-ARTIFACT-IS-A-VIEW-REPUBLISHED-FROM-THE-REPO`.

Quickstart lists the design systems the account can open; with no default, ask the PM which to attach.
The repo's design-system record names its tokens and points at the CSS that declares their values,
never copying them; a test checks each named token is still declared there.

## Review

- **Reviewers read the committed source**, never the link: `staff-ux` for flow, `senior-front-end` for
  design-system adherence. Neither holds the Artifact tool; the EM applies findings, commits, republishes.
- **People's canvas comments** are harvested, never skimmed: § Harvest before anything executes on it.
  Claude replies or resolves only on a thread a person sent to Claude, and cannot open one.
- **The Design type discourages visual verification.** For pixels, open `project/*.html` locally or take
  a Playwright screenshot; a review that rendered nothing says so.

## Harvest before anything executes on it

**A canvas is pulled down to a local record before a plan, brief or dispatch executes on it.** The
record is the source for execution; the link is never read. Token:
`A-CANVAS-IS-HARVESTED-BEFORE-ANYTHING-EXECUTES-ON-IT`. Layout, fields, reason codes and rationale:
`coordinator/docs/wiki/schema-and-validation-contracts/canvas-harvest-record.md`.

1. **When:** a canvas is approved, or a plan, brief or dispatch is about to cite it.
2. **How, in the main loop** (the Artifact tools are main-loop only): Artifact `list`, Artifact `read`,
   then a whole ArtifactComments `read` (a paged or thread-filtered read is refused). Then, at once, in
   the same sitting (saved frame files do not last), run the engine op `canvas-harvest harvest --url
   <artifact url> --out docs/design/<slug>/harvest --transcript <path>`, resolved per
   `snippets/resolve-coordinator-bin.md`. The EM retypes no frame or thread; the op lifts them to disk.
3. **Settle:** fill `harvest/SETTLED.md`, one `[thread:<id>]` item per decision (`[no-threads]` for a
   canvas with none), and commit the record in the same step. Thread files carry commenters' names and
   words verbatim, so a repo whose `docs/design/` is published keeps the record out of the published set.
4. **Cite:** a plan or brief names the record's `harvest/harvest.json` path. Execution reads the record,
   never the link. At execute entry, re-read the canvas and run `canvas-harvest probe`; drift means
   re-harvest and update `SETTLED.md`.
5. **Out of reach:** a canvas that cannot be read is refused with that reason. Republish from the committed
   files under the current login, or cite the committed source without the URL.

## Boundaries

- **`DesignSync` is not the canvas**: it syncs a local component library to a claude.ai design-system project.
- **The canvas needs an authenticated claude.ai session.** Without one, say so; never substitute a
  designer hand-off. A canvas already cited is not skipped: § Harvest.

## Worked examples (example-stats-repo)

- `docs/design/advanced-stats-canvas/`: a redesign canvas whose README carries the republish recipe; its
  `harvest/` holds the frames, the verbatim threads and `SETTLED.md` a plan cites.
- `design-system/cockpit/`: its `tokens.json` copies values and has drifted from Cockpit's `globals.css`,
  the failure the record rule above exists for.
