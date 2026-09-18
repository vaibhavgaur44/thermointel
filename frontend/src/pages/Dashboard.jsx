import { AlertOctagon } from "lucide-react";

import { GlobeCanvas } from "@/components/map/GlobeCanvas";
import { Map2D } from "@/components/map/Map2D";
import { FilterBar } from "@/components/layout/FilterBar";
import { TopBar } from "@/components/layout/TopBar";
import { AlertQueuePanel } from "@/components/panels/AlertQueuePanel";
import { PriorityEventsPanel } from "@/components/panels/PriorityEventsPanel";
import { RegionalOverviewPanel } from "@/components/panels/RegionalOverviewPanel";
import { SelectedEventPanel } from "@/components/panels/SelectedEventPanel";
import { useDashboard } from "@/state/DashboardContext";

const DemoBanner = () => (
  <div
    data-testid="demo-data-banner"
    className="pointer-events-auto flex items-center justify-center gap-2 bg-amber-400 px-4 py-1 font-mono text-[10px] font-bold uppercase tracking-[0.3em] text-amber-950"
  >
    <AlertOctagon className="h-3 w-3" />
    Demo data — development values only, not operational intelligence
  </div>
);

export default function Dashboard() {
  const { demoMode, selectedEventId, mapMode } = useDashboard();

  return (
    <div className="relative h-screen w-screen overflow-hidden bg-[#04060c]">
      {mapMode === "2D" ? <Map2D /> : <GlobeCanvas />}

      <div className="pointer-events-none absolute inset-0 z-10 flex flex-col">
        {demoMode && <DemoBanner />}
        <TopBar />

        <div className="flex px-4 pt-3">
          <FilterBar />
        </div>

        <div className="flex min-h-0 flex-1 items-start justify-between gap-4 p-4">
          <div className="flex w-[320px] shrink-0 flex-col gap-3">
            <RegionalOverviewPanel />
          </div>

          <div
            className="scroll-thin flex max-h-full w-[364px] shrink-0 flex-col gap-3 overflow-y-auto pb-1"
            data-testid="right-panel-column"
          >
            {selectedEventId ? (
              <SelectedEventPanel />
            ) : (
              <>
                <PriorityEventsPanel />
                <AlertQueuePanel />
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
