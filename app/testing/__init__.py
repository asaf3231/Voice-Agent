"""Alta Outbound Voice Agent — app.testing (offline stress-test infrastructure).

Single responsibility: package marker for the MOCK-BRIDGE and any other test-only
helpers the stress suite uses. Importing this package is side-effect free:
it defines nothing at import beyond the submodules it exposes on demand.
"""
