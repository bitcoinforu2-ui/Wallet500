# Wallet500 Iron Rules

## Iron Rule — verify before claiming completion

When the user marks a request, change, alert, workflow, sensor, fix, or behavior as a **"כלל ברזל" / iron rule**, implementation alone is not completion.

A task covered by an iron rule is complete only after the relevant end-to-end behavior has been verified in the real execution path or, when production execution cannot yet be observed, by the strongest available equivalent validation.

Required operating contract:

1. Implement the requested behavior in the actual production path, not only in documentation or a side script.
2. Add or update regression coverage for the failure mode whenever it is testable.
3. Verify configuration, routing, permissions/secrets dependencies, dedupe/state, and delivery/execution path that could silently suppress the requested behavior.
4. Run the relevant tests/guards and inspect their result.
5. When the requirement concerns a live output such as Telegram, dashboard publication, scheduled workflow, or alert delivery, verify the live path after deployment as soon as a qualifying production event or safe test path is available.
6. Do not tell the user "done", "fixed", "working", or equivalent until verification evidence supports that statement.
7. If production verification is still pending, state exactly that it is **implemented and test-passed, but live verification is pending**. Never imply otherwise.
8. If verification finds a defect, fix it and repeat validation without waiting for another approval when the existing authorization allows it.

This rule applies across Wallet500 work and takes precedence over optimistic completion reporting.
