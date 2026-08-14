# ZCoder Policy-as-Code Engine

## Overview
ZCoder provides a fine-grained, declarative policy-as-code engine allowing organizations to enforce security rules and attach obligations to actions:

- **Obligations Supported**:
  - `require_approval`: Mandatory operator approval for high-risk tools or deployment triggers.
  - `require_sandbox`: Enforced container/gVisor isolation for untrusted repositories.
  - `max_budget`: Automatic budget ceiling per execution.
  - `allowed_runtime`: Whitelist of runtime execution models.
- **Fail-Closed Evaluation**: Missing policies or evaluation errors default to DENY.
- **Explainability**: `zcoder policy explain` allows non-mutating simulation of policy evaluation.
