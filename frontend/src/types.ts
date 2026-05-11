export type JobStatus =
  | "queued"
  | "assigned"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export interface JobRead {
  id: string;
  title: string;
  status: JobStatus;
  input_bundle_path: string;
  assigned_at: string | null;
  started_at: string | null;
  status_changed_at: string;
  latest_checkpoint_path: string | null;
  last_checkpoint_at: string | null;
  progress: number | null;
  progress_codes: string[];
  checkpoint_cycle_status: string | null;
  checkpoint_cycle_failures: Array<{ code: string; detail: string }>;
  assigned_worker_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkerRead {
  id: string;
  platform: string;
  gpu_model: string;
  gpu_count: number;
  vram_gb: number;
  status: string;
  provider_id: string | null;
  provider_state: string | null;
  provider_state_raw: string | null;
  provider_reason: string | null;
  provider_last_checked_at: string | null;
  last_heartbeat: string;
  registered_at: string;
}

export interface ClusterConfig {
  name: string;
  partition: string;
  strategy: string;
  max_pending_jobs: number;
  wall_time: string;
  enabled: boolean;
}

export interface HealthStatus {
  status: string;
  version?: string;
  warnings: string[];
  tailscale?: {
    connected: boolean;
    hostname?: string;
    dns_name?: string;
    ip?: string;
    error?: string;
  };
}

export interface FrontendConfig {
  api_base_url: string;
  refresh_interval_seconds: number;
}

export interface DashboardPayload {
  jobs: JobRead[];
  workers: WorkerRead[];
  clusters: ClusterConfig[];
  health: HealthStatus;
}
