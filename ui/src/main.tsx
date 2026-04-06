import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import "./styles.css";

async function loadRuntimeConfig(): Promise<void> {
  await new Promise<void>((resolve) => {
    const script = document.createElement("script");
    script.src = "/runtime/config.js";
    script.onload = () => resolve();
    script.onerror = () => resolve();
    document.head.appendChild(script);
  });
}

void loadRuntimeConfig().finally(() => {
  ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
});
