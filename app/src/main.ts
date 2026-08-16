import { mount } from "svelte";

import "./app.css";
import App from "./App.svelte";
import { bootBridge, watchLateBoot } from "./bridge/bridge";

void bootBridge().catch((err: unknown) => {
  console.warn("[boot] initial bridge failed:", err);
});
watchLateBoot();

const app = mount(App, {
  target: document.getElementById("app")!,
});

export default app;
