import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import { SessionProvider } from "./app/session";
import { syncApiTokenFromStorage } from "./lib/api/client";
import "./index.css";

syncApiTokenFromStorage();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <SessionProvider>
      <App />
    </SessionProvider>
  </React.StrictMode>,
);
