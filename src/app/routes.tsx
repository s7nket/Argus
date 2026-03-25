import { createBrowserRouter } from "react-router";
import { ArgusLanding } from "./components/ArgusLanding";
import { DebateDashboard } from "./components/DebateDashboard";

export const router = createBrowserRouter([
  {
    path: "/",
    Component: ArgusLanding,
  },
  {
    path: "/dashboard",
    Component: DebateDashboard,
  }
]);