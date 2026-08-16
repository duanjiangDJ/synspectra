// Shared RPC contracts between the app and the desktop carrier.
// The desktop side implements the same method set; the browser dev mode talks
// to the identical protocol over a WebSocket carrier started by "desktop --headless".

export interface CategoryInfo {
  name: string;
  file_count: number;
}

export interface BackendPaths {
  repo_root: string | null;
  default_data_dir: string;
  data_dir: string;
  venv_python: string | null;
  uv: string | null;
  run_metrics: string | null;
  resource_manager: string | null;
  corpus_import: string | null;
  manifest: string | null;
  requirements_lock: string | null;
  env: Record<string, string>;
}

export interface SpawnRequest {
  program: string;
  args: string[];
  env: Record<string, string>;
}

export interface CsvPreview {
  headers: string[];
  rows: string[][];
}

export interface BootInfo {
  env: "desktop" | "web" | "test";
  platform: string;
  wsUrl: string;
  token: string;
  paths: BackendPaths | null;
}

export interface RpcError {
  code: string;
  message: string;
}

export interface RpcMethods {
  backend_paths: { params: { dataDir?: string }; result: BackendPaths };
  scan_source_dir: { params: { sourceDir: string }; result: CategoryInfo[] };
  scan_source_tree: { params: { sourceDir: string }; result: CategoryInfo[] };
  list_csv_files: { params: { resultDir: string }; result: string[] };
  read_csv_preview: { params: { path: string; maxRows?: number }; result: CsvPreview };
  path_exists: { params: { path: string }; result: boolean };
  set_always_on_top: { params: { enabled: boolean }; result: null };
  set_theme: { params: { theme: string }; result: null };
  open_in_file_manager: { params: { path: string }; result: null };
  choose_directory: { params: Record<string, never>; result: string | null };
  choose_zip_file: { params: Record<string, never>; result: string | null };
  spawn_backend: { params: { request: SpawnRequest }; result: number };
  kill_backend: { params: { childId: number }; result: null };
  bootstrap_runtime: {
    params: { uvPath: string; requirements: string; pythonVersion: string; dataDir: string };
    result: null;
  };
}

export type RpcMethod = keyof RpcMethods;

export interface RpcRequestEnvelope {
  id: number;
  method: RpcMethod;
  params: unknown;
  token: string;
}

export interface RpcResponseEnvelope {
  id: number;
  ok: boolean;
  result?: unknown;
  error?: RpcError;
}

export interface EventEnvelope {
  type: "event";
  stream: string;
  line: string;
}

export type ServerMessage = RpcResponseEnvelope | EventEnvelope;
