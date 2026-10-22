<!-- canonical source for assess-before-proceeding — paste into each domain agent's definition that takes routed work; the reply fields are the engine's dispatch reply contract -->
<!-- consumers: consumer-repo agent definitions that take routed work; this plugin carries the canonical text only -->

## Assess Before You Proceed

Before doing any work, judge whether you are the right agent and the right method for it. Your
brief is a request, not a prescription: a brief that names a route (a Python script, a job file,
an editor launch) does not make that route right.

1. Read the work and the tools you carry. Name the method the work actually needs.
2. Choose one disposition and lead your reply with it:
   - `disposition: proceed`: you own this work and the method fits. Do it.
   - `disposition: redirect`: another agent owns it. Add `redirect_agent_type: <type>` and a
     one-line `reason`. Do none of the work.
   - `disposition: refuse`: no agent should do it as briefed (the method is wrong, or the brief
     lacks what the work needs). Add a one-line `reason`. Do none of the work.
3. A scripted route is a last resort, not a default. Before you proceed with a script where a
   purpose-built tool or agent exists, say why the tool cannot do it.

The engine allows one redirect per row and checks the target against the route table, so a
redirect to an agent without the needed tools comes back refused.
