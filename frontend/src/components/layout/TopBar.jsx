import { Activity, Globe2, Layers, Radio } from "lucide-react";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { useIngestionStatus } from "@/hooks/useThermoIntel";
import { hasIonToken } from "@/map/viewer";
import { useDashboard } from "@/state/DashboardContext";

const BASEMAPS = [
  { value: "dark", label: "Dark" },
  { value: "satellite", label: "Satellite" },
  { value: "streets", label: "Streets" },
];

const PILL =
  "flex items-center gap-1.5 rounded-sm px-2.5 py-1.5 font-mono text-[10px] font-semibold uppercase tracking-[0.16em] transition-colors duration-200";

const ViewModeToggle = () => {
  const { filters, setViewMode } = useDashboard();
  return (
    <div
      className="flex items-center overflow-hidden rounded-sm border border-slate-700/60"
      data-testid="view-mode-toggle"
    >
      {[
        { value: "LIVE", label: "Live" },
        { value: "HISTORICAL", label: "Historical" },
      ].map((mode) => (
        <button
          key={mode.value}
          type="button"
          data-testid={`view-mode-${mode.value.toLowerCase()}`}
          onClick={() => setViewMode(mode.value)}
          className={`${PILL} ${
            filters.viewMode === mode.value
              ? "bg-emerald-400/15 text-emerald-300"
              : "text-slate-400 hover:bg-slate-700/40 hover:text-slate-200"
          }`}
        >
          {mode.value === "LIVE" && <Radio className="h-3 w-3" />}
          {mode.label}
        </button>
      ))}
    </div>
  );
};

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

const PipelineStatus = () => {
  const { data } = useIngestionStatus();
  const stages = [
    ["FIRMS", data?.firms_source_configured],
    ["Event formation", data?.event_formation_calibrated],
    ["ML models", data?.ml_models_available],
    ["Threat engine", data?.threat_engine_calibrated],
  ];

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          data-testid="pipeline-status-trigger"
          className={`${PILL} border border-slate-700/60 text-slate-300 hover:bg-slate-700/40`}
        >
          <Activity className="h-3 w-3 text-amber-400" />
          Pipeline
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        className="w-72 border-slate-700/50 bg-[#020817]/95 p-3 backdrop-blur-xl"
      >
        <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.2em] text-sky-300/70">
          Pipeline readiness
        </p>
        <ul className="mt-2 space-y-1.5" data-testid="pipeline-status-list">
          {stages.map(([label, ready]) => (
            <li
              key={label}
              className="flex items-center justify-between text-[12px] text-slate-300"
            >
              <span>{label}</span>
              <span
                className={`font-mono text-[10px] uppercase tracking-[0.14em] ${
                  ready ? "text-emerald-400" : "text-slate-300"
                }`}
              >
                {ready ? "Ready" : "Not configured"}
              </span>
            </li>
          ))}
        </ul>
        <p className="mt-3 border-t border-slate-800 pt-2 text-[11px] leading-relaxed text-slate-300">
          Ingestion, event formation, ML inference and threat scoring are
          delivered in later phases. No values are simulated.
        </p>
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
          ThermoIntel
          <span className="ml-1.5 font-mono text-[10px] font-medium tracking-[0.18em] text-sky-300/70">
            V2
          </span>
        </p>
        <p className="font-mono text-[9px] uppercase tracking-[0.24em] text-slate-300">
          India thermal-event intelligence
        </p>
      </div>
    </div>
    <div className="flex items-center gap-2">
      <ViewModeToggle />
      <PipelineStatus />
      <BasemapSelector />
      <MapModeToggle />
    </div>
  </header>
);
