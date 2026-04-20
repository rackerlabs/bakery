import { describe, expect, it } from "vitest";

import { buildCollectorParameters } from "./collectors";

const clusterInventoryCollector = {
  collector_type: "cluster_inventory",
  label: "Cluster inventory",
  description: "Inventory collector",
  default_parameters: { limit: 50 },
  example_parameters: { namespace: "example-namespace", limit: 25 },
  parameters: [
    {
      name: "namespace",
      label: "Namespace",
      field_type: "text",
      description: "Namespace to inspect",
      required: false,
      default_value: "",
      placeholder: "example-namespace",
    },
    {
      name: "limit",
      label: "Row limit",
      field_type: "number",
      description: "Maximum rows",
      required: false,
      default_value: 50,
      placeholder: "50",
    },
  ],
};

describe("buildCollectorParameters", () => {
  it("merges typed form values with default parameters and advanced overrides", () => {
    const params = buildCollectorParameters(
      clusterInventoryCollector,
      {
        namespace: "example-namespace",
        limit: "25",
      },
      '{"extra":true,"limit":10}',
    );

    expect(params).toEqual({
      namespace: "example-namespace",
      limit: 10,
      extra: true,
    });
  });

  it("rejects invalid advanced json", () => {
    expect(() =>
      buildCollectorParameters(clusterInventoryCollector, { namespace: "", limit: "" }, "{"),
    ).toThrow(/advanced parameters/i);
  });
});
