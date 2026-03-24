"""Hook system — mirrors OpenClaw's src/hooks/ module.

Public surface:
- Types: HookEvent, HookHandler, HookRegistration
- Runner: HookRunner
- Frontmatter: parse_hook_frontmatter, discover_hooks
- Loader: load_bundled_hooks, load_workspace_hooks
- Bundled hooks: AuditLoggerHook, SafetyGuardHook, ScopeEnforcerHook
"""
