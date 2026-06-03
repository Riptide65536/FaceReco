import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
} from "react-router-dom";

import { useSession } from "./session";
import { AppShell } from "../components/AppShell";
import { LoginPage } from "../pages/LoginPage";
import { OverviewPage } from "../pages/OverviewPage";
import { CamerasPage } from "../pages/CamerasPage";
import { FacesPage } from "../pages/FacesPage";
import { LogsPage } from "../pages/LogsPage";
import { SystemPage } from "../pages/SystemPage";

function ProtectedRoutes() {
  const { isAuthenticated } = useSession();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <AppShell />;
}

export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<ProtectedRoutes />}>
          <Route path="/" element={<Navigate to="/overview" replace />} />
          <Route path="/overview" element={<OverviewPage />} />
          <Route path="/cameras" element={<CamerasPage />} />
          <Route path="/faces" element={<FacesPage />} />
          <Route path="/logs" element={<LogsPage />} />
          <Route path="/system" element={<SystemPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
