"""Context Debugger: local, read-only observability for OpenCode context.

Observation tool, not an intervention tool. It records each
OpenCode model-visible context at the V2 session context hook, lets an
operator inspect and query how it was assembled, tracks session change,
and surfaces measurable conditions — without modifying any context.

Boundary: ``opencode.v2.model_context`` — the OpenCode V2 semantic
model-request context observed immediately before the agent model
request proceeds. This is NOT the byte-for-byte provider HTTP request,
provider-added material, the wire representation, or the provider cache
decision. Reports state this explicitly.
"""

DEBUGGER_VERSION = "0.1.0"
