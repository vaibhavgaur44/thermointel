import { ChevronDown, Filter, RotateCcw } from "lucide-react";

import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  CLASSIFICATION_FILTERS,
  SOURCE_TYPES,
  TIME_RANGES,
  eventTypeMeta,
} from "@/constants/taxonomy";
import { useRegions } from "@/hooks/useThermoIntel";
import { useDashboard } from "@/state/DashboardContext";

const BAR =
  "pointer-events-auto flex items-center gap-1 rounded-xl border border-slate-600/35 bg-[#020817]/80 px-1.5 py-1.5 backdrop-blur-xl";

const TRIGGER =
  "flex items-center gap-1.5 rounded-sm px-2.5 py-1.5 font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-300 transition-colors duration-200 hover:bg-slate-700/40 hover:text-slate-50";

const GeographyFilter = () => {
  const { filters, setRegion } = useDashboard();
  const { data } = useRegions();
  const regions = data?.regions || [];

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button type="button" data-testid="filter-geography-trigger" className={TRIGGER}>
          {filters.region?.name || "India"}
          <ChevronDown className="h-3 w-3 text-slate-300" />
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        className="max-h-80 w-72 overflow-y-auto rounded-xl border border-slate-600/40 bg-[#020817]/95 p-1 shadow-2xl"
      >
        <button
          type="button"
          data-testid="filter-geography-india"
          onClick={() => setRegion(null)}
          className="w-full rounded-sm px-2 py-1.5 text-left text-[12px] text-slate-200 transition-colors duration-150 hover:bg-sky-400/10 hover:text-sky-200"
        >
          India (all states &amp; UTs)
        </button>
        <div className="my-1 h-px bg-slate-800" />
        {regions.map((region) => (
          <button
            key={region.name}
            type="button"
            data-testid={`filter-geography-option-${region.name.toLowerCase().replace(/\s+/g, "-")}`}
            onClick={() => setRegion({ name: region.name, bbox: region.bbox })}
            className={`flex w-full items-center justify-between rounded-sm px-2 py-1.5 text-left text-[12px] transition-colors duration-150 hover:bg-sky-400/10 ${
              filters.region?.name === region.name
                ? "text-sky-300"
                : "text-slate-300"
            }`}
          >
            <span className="truncate">{region.name}</span>
            <span className="ml-2 shrink-0 font-mono text-[9px] uppercase tracking-[0.14em] text-slate-400">
              {region.kind === "UNION_TERRITORY" ? "UT" : "ST"}
            </span>
          </button>
        ))}
      </PopoverContent>
    </Popover>
  );
};

const ClassificationFilter = () => {
  const { filters, toggleClassification } = useDashboard();
  return (
    <div className="flex items-center gap-1" data-testid="filter-classification">
      {CLASSIFICATION_FILTERS.map((value) => {
        const meta = eventTypeMeta(value);
        const active = filters.classifications.includes(value);
        return (
          <button
            key={value}
            type="button"
            data-testid={`filter-classification-${value.toLowerCase()}`}
            onClick={() => toggleClassification(value)}
            className="flex items-center gap-1.5 rounded-sm border px-2 py-1.5 font-mono text-[10px] font-semibold uppercase tracking-[0.14em] transition-colors duration-200"
            style={{
              borderColor: active ? `${meta.color}80` : "rgba(51,65,85,0.6)",
              backgroundColor: active ? `${meta.color}1c` : "transparent",
              color: active ? meta.color : "#94a3b8",
            }}
          >
            <span
              className="h-1.5 w-1.5 rounded-full"
              style={{ backgroundColor: meta.color }}
            />
            {meta.short}
          </button>
        );
      })}
    </div>
  );
};

const SourceTypeFilter = () => {
  const { filters, toggleSourceType } = useDashboard();
  const count = filters.sourceTypes.length;

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button type="button" data-testid="filter-source-type-trigger" className={TRIGGER}>
          Source type
          {count > 0 && (
            <span className="rounded-sm bg-sky-400/20 px-1 text-[9px] text-sky-300">
              {count}
            </span>
          )}
          <ChevronDown className="h-3 w-3 text-slate-300" />
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        className="max-h-80 w-72 overflow-y-auto rounded-xl border border-slate-600/40 bg-[#020817]/95 p-1 shadow-2xl"
      >
        {Object.entries(SOURCE_TYPES).map(([value, label]) => {
          const active = filters.sourceTypes.includes(value);
          return (
            <button
              key={value}
              type="button"
              data-testid={`filter-source-type-${value.toLowerCase()}`}
              onClick={() => toggleSourceType(value)}
              className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-[12px] transition-colors duration-150 hover:bg-sky-400/10"
            >
              <span
                className={`flex h-3 w-3 shrink-0 items-center justify-center rounded-[2px] border ${
                  active
                    ? "border-sky-400 bg-sky-400/80"
                    : "border-slate-600 bg-transparent"
                }`}
              />
              <span className={active ? "text-sky-200" : "text-slate-300"}>
                {label}
              </span>
            </button>
          );
        })}
      </PopoverContent>
    </Popover>
  );
};

const TimeRangeFilter = () => {
  const { filters, setTimeRange } = useDashboard();
  return (
    <div
      className="flex items-center overflow-hidden rounded-sm border border-slate-700/60"
      data-testid="filter-time-range"
    >
      {TIME_RANGES.map((range) => (
        <button
          key={range.value}
          type="button"
          data-testid={`filter-time-${range.value}`}
          onClick={() => setTimeRange(range.value)}
          className={`px-2.5 py-1.5 font-mono text-[10px] font-semibold uppercase tracking-[0.14em] transition-colors duration-200 ${
            filters.timeRange === range.value
              ? "bg-sky-400/20 text-sky-300"
              : "text-slate-400 hover:bg-slate-700/40 hover:text-slate-200"
          }`}
        >
          {range.label}
        </button>
      ))}
    </div>
  );
};

export const FilterBar = () => {
  const { resetFilters } = useDashboard();
  return (
    <div className={BAR} data-testid="filter-bar">
      <Filter className="mx-1.5 h-3.5 w-3.5 shrink-0 text-slate-300" />
      <GeographyFilter />
      <span className="h-5 w-px bg-slate-700/60" />
      <ClassificationFilter />
      <span className="h-5 w-px bg-slate-700/60" />
      <SourceTypeFilter />
      <span className="h-5 w-px bg-slate-700/60" />
      <TimeRangeFilter />
      <button
        type="button"
        data-testid="filter-reset-button"
        onClick={resetFilters}
        className="ml-1 rounded-sm p-1.5 text-slate-300 transition-colors duration-200 hover:bg-slate-700/40 hover:text-slate-200"
        aria-label="Reset filters"
      >
        <RotateCcw className="h-3.5 w-3.5" />
      </button>
    </div>
  );
};
