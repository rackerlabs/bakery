import type { CollectionCollector, CollectionCollectorField } from "../contracts";

export const JOB_STATUS_COPY: Record<string, string> = {
  queued: "Waiting for the PoundCake monitor to claim and run the collector.",
  leased: "A PoundCake monitor has claimed the job and is actively collecting data.",
  succeeded: "Collection completed successfully and the structured result is available below.",
  failed: "Collection ran but the PoundCake-side collector returned an error.",
  timed_out: "The monitor claimed the job but never completed it before the lease expired.",
};

function normalizeFieldValue(field: CollectionCollectorField, rawValue: string): unknown {
  const trimmed = rawValue.trim();
  if (!trimmed) {
    return undefined;
  }
  if (field.field_type === "number") {
    const parsed = Number(trimmed);
    if (!Number.isFinite(parsed)) {
      throw new Error(`${field.label} must be a valid number`);
    }
    return parsed;
  }
  return trimmed;
}

export function buildCollectorParameters(
  collector: CollectionCollector,
  fieldValues: Record<string, string>,
  advancedJson: string,
): Record<string, unknown> {
  const params: Record<string, unknown> = { ...collector.default_parameters };

  collector.parameters.forEach((field) => {
    const rawValue = fieldValues[field.name] ?? "";
    const normalized = normalizeFieldValue(field, rawValue);
    if (normalized === undefined) {
      if (field.required && params[field.name] === undefined) {
        throw new Error(`${field.label} is required`);
      }
      return;
    }
    params[field.name] = normalized;
  });

  const trimmedAdvancedJson = advancedJson.trim();
  if (!trimmedAdvancedJson) {
    return params;
  }

  let advanced: unknown;
  try {
    advanced = JSON.parse(trimmedAdvancedJson);
  } catch (error) {
    throw new Error(
      error instanceof Error ? `Advanced parameters: ${error.message}` : "Advanced parameters are invalid JSON",
    );
  }
  if (!advanced || typeof advanced !== "object" || Array.isArray(advanced)) {
    throw new Error("Advanced parameters must be a JSON object");
  }
  return { ...params, ...(advanced as Record<string, unknown>) };
}

export function getCollectorByType(
  collectors: CollectionCollector[],
  collectorType: string,
): CollectionCollector | undefined {
  return collectors.find((collector) => collector.collector_type === collectorType);
}
