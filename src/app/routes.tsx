import { createBrowserRouter } from "react-router";
import { ArgusLanding } from "./components/ArgusLanding";
import { DebateDashboard } from "./components/DebateDashboard";
import { DebateReplay } from "./components/DebateReplay";

export const router = createBrowserRouter([
  {
    path: "/",
    Component: ArgusLanding,
  },
  {
    path: "/debate-dashboard",
    Component: DebateDashboard,
  },
  {
    path: "/debate/:debateId",
    Component: DebateReplay,
  }
]);