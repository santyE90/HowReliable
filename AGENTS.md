<!-- BEGIN AWS Agent Toolkit rules -->
# AWS Guidance

- Where these AWS rules conflict with the project's own instructions, the
  project's instructions take precedence.
- Prefer the AWS MCP Server for AWS interactions — it provides sandboxed
  execution, observability, and audit logging. If unavailable, use the
  AWS CLI directly.
- Before starting a task, check whether a relevant AWS skill is available.
  Load the skill with `retrieve_skill` and prefer its guidance over
  general knowledge.
- When uncertain about specific AWS details (API parameters, permissions,
  limits, error codes), verify against documentation rather than guessing.
  State uncertainty explicitly if you cannot confirm.
- When creating infrastructure, prefer infrastructure-as-code (AWS CDK or
  CloudFormation) over direct CLI commands.
- When working with infrastructure, follow AWS Well-Architected Framework
  principles.
- Do not use em dashes in AWS resource names or descriptions. Use
  hyphens instead.

## Secret Safety

- MUST load the `aws-secrets-manager` skill first for any secret,
  credential, API key, token, or password task. MUST NOT call
  `secretsmanager get-secret-value` or `batch-get-secret-value`, and MUST
  NOT hit the Secrets Manager Agent daemon directly. MUST use
  `{{resolve:secretsmanager:secret-id:SecretString:json-key}}` with
  `asm-exec` so the secret resolves at runtime without entering context.
<!-- END AWS Agent Toolkit rules -->

<!-- BEGIN HowReliable existing deployment guardrails -->
# Existing HowReliable deployment

- This repository corresponds to existing AWS infrastructure, not a new project.
- Use AWS account `660097708945`, workload region `us-east-2`, and the existing
  SSO profile `SantyE90`. Verify the authenticated account before AWS work.
- Do not guess SSO settings, create a new AWS account, or create long-lived keys.
- The original Terraform state is on another computer. Do not initialize new
  infrastructure state or run Terraform apply, destroy, or import.
- Do not deploy, modify, delete, or recreate AWS resources without explicit user
  approval. Current setup authorization covers local development tools, AWS MCP,
  skills, and agent guardrails only; cloud verification must be read-only.
- ECS was manually scaled to desired count 0 to reduce costs. Preserve that
  setting. The ALB may still incur charges. Terraform declares desired count 1;
  a future apply could undo the manual scale-down.
- Do not build or push Docker images during local setup.
- Ask before making changes outside the local development environment.
- Inspect existing tools and configuration before installing or replacing them.
- Agent Toolkit service calls may require `us-east-1`; keep that explicit service
  region separate from the workload profile's `us-east-2` default.
<!-- END HowReliable existing deployment guardrails -->
