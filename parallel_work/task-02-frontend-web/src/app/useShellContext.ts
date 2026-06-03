import { useOutletContext } from "react-router-dom";

import type { ApiMode, SystemStatus } from "../lib/api/types";

export interface ShellContextValue {
  apiMode: ApiMode;
  statusLoading: boolean;
  statusRefreshing: boolean;
  systemStatus?: SystemStatus;
  refreshSystemStatus: () => Promise<void>;
}

export function useShellContext() {
  return useOutletContext<ShellContextValue>();
}
