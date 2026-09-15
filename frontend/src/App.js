import { Toaster } from "sonner";

import Dashboard from "@/pages/Dashboard";
import { DashboardProvider } from "@/state/DashboardContext";

export default function App() {
  return (
    <DashboardProvider>
      <Dashboard />
      <Toaster
        theme="dark"
        position="bottom-center"
        toastOptions={{
          style: {
            background: "rgba(7,11,20,0.92)",
            border: "1px solid rgba(51,65,85,0.6)",
            color: "#e2e8f0",
            backdropFilter: "blur(12px)",
            borderRadius: "4px",
            fontSize: "12px",
          },
        }}
      />
    </DashboardProvider>
  );
}
