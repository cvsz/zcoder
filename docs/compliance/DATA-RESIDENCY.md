# ZCoder Data Residency Enforcement

## Policy Enforcement
Residency policies are evaluated before job scheduling:
1. Candidate worker region must exist in `allowed_worker_regions`.
2. Selected LLM inference geo must exist in `allowed_provider_inference_regions`.
3. Failover routing never permits cross-border data transfer unless `cross_region_transfer_allowed: true`.
