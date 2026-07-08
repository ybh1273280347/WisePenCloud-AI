type DebugDetails = Record<string, unknown>;

const enabled = import.meta.env.DEV && localStorage.getItem("wisepen:debug") === "1";

function write(level: "log" | "warn" | "error", message: string, details?: DebugDetails) {
  if (!enabled && level !== "error") {
    return;
  }

  const payload = details ? pruneDetails(details) : undefined;

  if (payload) {
    console[level](`[wisepen] ${message}`, payload);
    return;
  }

  console[level](`[wisepen] ${message}`);
}

function pruneDetails(details: DebugDetails) {
  return Object.fromEntries(
    Object.entries(details).map(([key, value]) => [key, summarizeValue(value)]),
  );
}

function summarizeValue(value: unknown): unknown {
  if (typeof value === "string") {
    return value.length > 500 ? `${value.slice(0, 500)}... (${value.length} chars)` : value;
  }

  if (Array.isArray(value)) {
    return {
      type: "array",
      length: value.length,
    };
  }

  if (value instanceof Error) {
    return {
      name: value.name,
      message: value.message,
      stack: value.stack,
    };
  }

  if (value instanceof Headers) {
    return Object.fromEntries(value.entries());
  }

  if (value && typeof value === "object") {
    return summarizeObject(value);
  }

  return value;
}

function summarizeObject(value: object) {
  const entries = Object.entries(value).slice(0, 20);
  return Object.fromEntries(
    entries.map(([key, entryValue]) => {
      if (typeof entryValue === "string") {
        return [key, summarizeValue(entryValue)];
      }

      if (Array.isArray(entryValue)) {
        return [key, { type: "array", length: entryValue.length }];
      }

      if (entryValue && typeof entryValue === "object") {
        return [key, `[${entryValue.constructor.name}]`];
      }

      return [key, entryValue];
    }),
  );
}

export const debugLog = {
  error(message: string, details?: DebugDetails) {
    write("error", message, details);
  },
  log(message: string, details?: DebugDetails) {
    write("log", message, details);
  },
  warn(message: string, details?: DebugDetails) {
    write("warn", message, details);
  },
};
