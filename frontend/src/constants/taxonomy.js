/**
 * Presentation vocabulary mirroring the frozen Phase 1 taxonomy.
 * Labels and colours only - no classification logic lives in the frontend.
 */

export const EVENT_TYPES = {
  INDUSTRIAL_FIRE: {
    label: "Industrial Fire",
    short: "Industrial Fire",
    category: "INDUSTRIAL",
    color: "#FF3B30",
    marker: "pin",
  },
  PERSISTENT_HEAT_SOURCE: {
    label: "Persistent Heat Source",
    short: "Persistent Heat",
    category: "INDUSTRIAL",
    color: "#3B82F6",
    marker: "soft",
  },
  FOREST_FIRE: {
    label: "Forest Fire",
    short: "Forest Fire",
    category: "AGRICULTURAL",
    color: "#047857",
    marker: "soft",
  },
  AGRICULTURAL_FIRE: {
    label: "Agricultural Fire",
    short: "Agricultural Fire",
    category: "AGRICULTURAL",
    color: "#4ADE80",
    marker: "soft",
  },
  UNKNOWN_AGRICULTURAL_FIRE: {
    label: "Unknown Agricultural Fire",
    short: "Unknown Agri.",
    category: "AGRICULTURAL",
    color: "#A3E635",
    marker: "soft",
  },
};

/** Order used by the Regional Overview panel. */
export const OVERVIEW_ORDER = [
  "AGRICULTURAL_FIRE",
  "FOREST_FIRE",
  "PERSISTENT_HEAT_SOURCE",
  "INDUSTRIAL_FIRE",
  "UNKNOWN_AGRICULTURAL_FIRE",
];

/** The four classification filters defined in Phase 1, section 19. */
export const CLASSIFICATION_FILTERS = [
  "AGRICULTURAL_FIRE",
  "FOREST_FIRE",
  "INDUSTRIAL_FIRE",
  "PERSISTENT_HEAT_SOURCE",
];

export const UNCLASSIFIED = {
  label: "Unclassified",
  color: "#64748B",
  marker: "soft",
};

export const SOURCE_TYPES = {
  GAS_FLARE: "Gas Flare",
  POWER_PLANT: "Power Plant",
  OIL_REFINERY_PETROCHEMICAL: "Oil Refinery / Petrochemical",
  STEEL_METAL: "Steel / Metal",
  CEMENT_KILN: "Cement / Kiln",
  BRICK_KILN: "Brick Kiln",
  CHEMICAL: "Chemical",
  FOUNDRY_SMELTING: "Foundry / Smelting",
  INDUSTRIAL_FURNACE_BOILER: "Industrial Furnace / Boiler",
  WASTE_INCINERATION: "Waste Incineration",
  MINING_MINERAL_PROCESSING: "Mining / Mineral Processing",
  OTHER_PERSISTENT_INDUSTRIAL_SOURCE: "Other Persistent Industrial Source",
  UNKNOWN_PERSISTENT_SOURCE: "Unknown Persistent Source",
};

export const THREAT_LEVELS = {
  LOW: { label: "LOW", color: "#10B981", rank: 1 },
  MODERATE: { label: "MODERATE", color: "#F59E0B", rank: 2 },
  HIGH: { label: "HIGH", color: "#EF4444", rank: 3 },
  CRITICAL: { label: "CRITICAL", color: "#DC2626", rank: 4 },
};

export const TIME_RANGES = [
  { value: "1h", label: "1H" },
  { value: "6h", label: "6H" },
  { value: "24h", label: "24H" },
  { value: "1w", label: "1W" },
];

export const eventTypeMeta = (eventType) =>
  EVENT_TYPES[eventType] || UNCLASSIFIED;

export const sourceTypeLabel = (sourceType) =>
  sourceType ? SOURCE_TYPES[sourceType] || sourceType : null;

export const threatMeta = (level) =>
  THREAT_LEVELS[level] || { label: "UNASSESSED", color: "#64748B", rank: 0 };
