/**
 * zcoder-sdk.ts — Official ZCoder TypeScript SDK Client
 *
 * Provides type-safe client methods for Node and backend TypeScript environments:
 *  • getEntitlements()
 *  • createJob(task, options)
 *  • registerWebhook(url, eventTypes)
 */

export interface EntitlementBundle {
  version: string;
  max_projects: number;
  max_repositories: number;
  monthly_budget_usd: number;
  concurrent_jobs: number;
  managed_agents: boolean;
  multiagent_orchestration: boolean;
  scim_enabled: boolean;
  sso_oidc_enabled: boolean;
}

export interface JobCreateResponse {
  id: string;
  organization_id: string;
  project_id?: string;
  task: string;
  status: string;
  created_at: number;
  request_id: string;
}

export interface WebhookRegisterResponse {
  id: string;
  url: string;
  secret: string;
  event_types: string[];
  status: string;
  created_at: number;
  request_id: string;
}

export class ZCoderClient {
  private apiKey: string;
  private organizationId: string;
  private projectId?: string;
  private baseUrl: string;

  constructor(config: { apiKey: string; organizationId: string; projectId?: string; baseUrl?: string }) {
    this.apiKey = config.apiKey;
    this.organizationId = config.organizationId;
    this.projectId = config.projectId;
    this.baseUrl = config.baseUrl || "https://api.zcoder.ai";
  }

  async getEntitlements(): Promise<EntitlementBundle> {
    const res = await fetch(`${this.baseUrl}/api/v1/entitlements`, {
      headers: {
        Authorization: `Bearer ${this.apiKey}`,
        "X-Organization-Id": this.organizationId,
      },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to get entitlements`);
    const data = (await res.json()) as { entitlements: EntitlementBundle };
    return data.entitlements;
  }

  async createJob(task: string, options?: { idempotencyKey?: string }): Promise<JobCreateResponse> {
    const headers: Record<string, string> = {
      Authorization: `Bearer ${this.apiKey}`,
      "X-Organization-Id": this.organizationId,
      "Content-Type": "application/json",
    };
    if (options?.idempotencyKey) {
      headers["Idempotency-Key"] = options.idempotencyKey;
    }
    const res = await fetch(`${this.baseUrl}/api/v1/jobs`, {
      method: "POST",
      headers,
      body: JSON.stringify({ task, project_id: this.projectId }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to create job`);
    return (await res.json()) as JobCreateResponse;
  }

  async registerWebhook(url: string, eventTypes: string[] = ["job.completed"]): Promise<WebhookRegisterResponse> {
    const res = await fetch(`${this.baseUrl}/api/v1/webhooks`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${this.apiKey}`,
        "X-Organization-Id": this.organizationId,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ url, event_types: eventTypes }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to register webhook`);
    return (await res.json()) as WebhookRegisterResponse;
  }
}
