import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import { initAdminFromUrl } from "./api/client.js";
import "./index.css";

// One-time owner activation: visiting /?admin=<ADMIN_TOKEN> stores the
// bypass token in localStorage, then the query param is removed from the URL.
initAdminFromUrl();

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
