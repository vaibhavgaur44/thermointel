import { Globe2, Layers } from "lucide-react";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { hasIonToken } from "@/map/viewer";
import { useDashboard } from "@/state/DashboardContext";

const BASEMAPS = [
  { value: "dark", label: "Dark" },
  { value: "satellite", label: "Satellite" },
  { value: "streets", label: "Streets" },
];

const PILL =
  "flex items-center gap-1.5 rounded-sm px-2.5 py-1.5 font-mono text-[10px] font-semibold uppercase tracking-[0.16em] transition-colors duration-200";

const BasemapSelector = () => {
  const { basemap, setBasemap } = useDashboard();
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          data-testid="basemap-trigger"
          className={`${PILL} border border-slate-700/60 text-slate-300 hover:bg-slate-700/40`}
        >
          <Layers className="h-3 w-3" />
          {BASEMAPS.find((b) => b.value === basemap)?.label}
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        className="w-44 rounded-xl border border-slate-600/40 bg-[#020817]/95 p-1 shadow-2xl"
      >
        {BASEMAPS.map((option) => (
          <button
            key={option.value}
            type="button"
            data-testid={`basemap-option-${option.value}`}
            onClick={() => setBasemap(option.value)}
            className={`flex w-full items-center justify-between rounded-sm px-2 py-1.5 text-left text-[12px] transition-colors duration-150 ${
              basemap === option.value
                ? "bg-sky-400/10 text-sky-300"
                : "text-slate-300 hover:bg-sky-400/10"
            }`}
          >
            {option.label}
            {option.value === "satellite" && (
              <span className="font-mono text-[9px] uppercase tracking-[0.12em] text-slate-400">
                {hasIonToken ? "Ion" : "Esri"}
              </span>
            )}
          </button>
        ))}
      </PopoverContent>
    </Popover>
  );
};

const MapModeToggle = () => {
  const { mapMode, setMapMode } = useDashboard();

  return (
    <div
      className="flex items-center overflow-hidden rounded-sm border border-slate-700/60"
      data-testid="map-mode-toggle"
    >
      {["2D", "3D"].map((mode) => (
        <button
          key={mode}
          type="button"
          data-testid={`map-mode-${mode.toLowerCase()}`}
          onClick={() => setMapMode(mode)}
          className={`${PILL} ${
            mapMode === mode
              ? "bg-sky-400/15 text-sky-300"
              : "text-slate-400 hover:bg-slate-700/40 hover:text-slate-200"
          }`}
        >
          {mode}
        </button>
      ))}
    </div>
  );
};

export const TopBar = () => (
  <header
    className="pointer-events-auto flex items-center justify-between gap-4 border-b border-slate-700/50 bg-[#020817]/80 px-5 py-2.5 backdrop-blur-xl"
    data-testid="top-bar"
  >
    <div className="flex items-center gap-3">
      <Globe2 className="h-4 w-4 text-sky-400" />
      <div className="leading-tight">
        <p className="text-[15px] font-bold tracking-tight text-slate-50">
          THERMOINTEL
        </p>
        <p className="font-mono text-[9px] uppercase tracking-[0.24em] text-slate-300">
          INDIA'S THERMAL-EVENT INTELLIGENCE
        </p>
      </div>
    </div>
    <div className="flex items-center gap-2">
      <BasemapSelector />
      <MapModeToggle />
    </div>
  </header>
);
