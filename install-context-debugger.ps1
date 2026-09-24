# install-context-debugger.ps1 — RETIRED.
#
# The manual global-copy installer has been replaced by the canonical
# Git package. Do not revive per-file copy logic.
#
# Install with:
#   opencode plugin add github:ernanhughes/project-context-opencode
#
# Then enable explicitly per process (see that repository's README):
#   PROJECT_CONTEXT_CAPTURE=1 (+ optional PROJECT_CONTEXT_SPOOL_DIR)
#   PROJECT_CONTEXT_RUNTIME=inject (+ block file and trace dir)
#
# Liveness is proven by that repository's smoke test, not by this script.

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "INSTALL RETIRED" -ForegroundColor Red
Write-Host "The manual Context Debugger installer is retired."
Write-Host ""
Write-Host "Install the canonical package instead:" -ForegroundColor Cyan
Write-Host "  opencode plugin add github:ernanhughes/project-context-opencode"
Write-Host ""
Write-Host "See docs/opencode-integration.md."
exit 1
