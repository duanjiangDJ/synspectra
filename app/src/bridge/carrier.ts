import type {
  EventEnvelope,
  RpcError,
  RpcMethod,
  RpcRequestEnvelope,
  RpcResponseEnvelope,
  ServerMessage,
} from "./contracts";

export type ConnectionState = "disconnected" | "connecting" | "connected";

export class CarrierError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = "CarrierError";
    this.code = code;
  }
}

interface PendingRequest {
  resolve: (value: unknown) => void;
  reject: (error: Error) => void;
}

/** WebSocket client for the desktop carrier. One RPC round trip = one JSON message. */
export class Carrier {
  private ws: WebSocket | null = null;
  private seq = 0;
  private pending = new Map<number, PendingRequest>();
  private listeners = new Map<string, Set<(line: string) => void>>();
  private _state: ConnectionState = "disconnected";
  private onStateChange: ((state: ConnectionState) => void) | null = null;

  constructor(
    private readonly wsUrl: string,
    private readonly token: string,
  ) {}

  get state(): ConnectionState {
    return this._state;
  }

  setStateListener(callback: ((state: ConnectionState) => void) | null): void {
    this.onStateChange = callback;
  }

  private setState(next: ConnectionState): void {
    if (this._state === next) return;
    this._state = next;
    this.onStateChange?.(next);
  }

  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        resolve();
        return;
      }
      this.setState("connecting");
      const url =
        this.wsUrl +
        (this.wsUrl.includes("?") ? "&" : "?") +
        "token=" + encodeURIComponent(this.token);
      const ws = new WebSocket(url);
      this.ws = ws;

      ws.onopen = () => {
        this.setState("connected");
        resolve();
      };
      ws.onerror = () => {
        this.setState("disconnected");
        const err = new CarrierError(
          "CARRIER_UNREACHABLE",
          "Cannot reach the bridge carrier at " + this.wsUrl,
        );
        for (const pending of this.pending.values()) pending.reject(err);
        this.pending.clear();
        reject(err);
      };
      ws.onclose = () => {
        this.setState("disconnected");
        const err = new CarrierError(
          "CARRIER_CLOSED",
          "The bridge carrier connection was closed.",
        );
        for (const pending of this.pending.values()) pending.reject(err);
        this.pending.clear();
      };
      ws.onmessage = (event) => {
        let message: ServerMessage;
        try {
          message = JSON.parse(String(event.data)) as ServerMessage;
        } catch {
          return;
        }
        if ("type" in message && message.type === "event") {
          const envelope = message as EventEnvelope;
          const callbacks = this.listeners.get(envelope.stream);
          if (callbacks) {
            for (const callback of [...callbacks]) callback(envelope.line);
          }
          return;
        }
        const response = message as RpcResponseEnvelope;
        const pending = this.pending.get(response.id);
        if (!pending) return;
        this.pending.delete(response.id);
        if (response.ok) {
          pending.resolve(response.result);
        } else {
          const error = (response.error ?? {
            code: "CARRIER_ERROR",
            message: "Unknown carrier error",
          }) as RpcError;
          pending.reject(new CarrierError(error.code, error.message));
        }
      };
    });
  }

  request<T>(method: RpcMethod, params: unknown): Promise<T> {
    const ws = this.ws;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      return Promise.reject(
        new CarrierError("CARRIER_OFFLINE", "The bridge carrier connection is not open."),
      );
    }
    const id = ++this.seq;
    const envelope: RpcRequestEnvelope = { id, method, params, token: this.token };
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve: resolve as (value: unknown) => void, reject });
      try {
        ws.send(JSON.stringify(envelope));
      } catch (err) {
        this.pending.delete(id);
        reject(err);
      }
    });
  }

  /** Subscribe to a named event stream. Returns an unsubscribe function. */
  on(stream: string, callback: (line: string) => void): () => void {
    let callbacks = this.listeners.get(stream);
    if (!callbacks) {
      callbacks = new Set();
      this.listeners.set(stream, callbacks);
    }
    callbacks.add(callback);
    return () => {
      callbacks?.delete(callback);
    };
  }

  close(): void {
    const err = new CarrierError("CARRIER_CLOSED", "The bridge carrier was shut down.");
    for (const pending of this.pending.values()) pending.reject(err);
    this.pending.clear();
    this.ws?.close();
    this.ws = null;
    this.setState("disconnected");
  }
}
