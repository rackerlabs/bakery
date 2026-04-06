import { useState } from "react";

export function JsonPanel({
  title,
  value,
  filename,
}: {
  title: string;
  value: unknown;
  filename: string;
}) {
  const [copied, setCopied] = useState(false);
  const serialized = JSON.stringify(value, null, 2);

  async function handleCopy() {
    await navigator.clipboard.writeText(serialized);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  }

  function handleDownload() {
    const blob = new Blob([serialized], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="json-panel">
      <div className="panel-header">
        <h3>{title}</h3>
        <div className="panel-actions">
          <button type="button" className="ghost-button" onClick={() => void handleCopy()}>
            {copied ? "Copied" : "Copy JSON"}
          </button>
          <button type="button" className="ghost-button" onClick={handleDownload}>
            Export JSON
          </button>
        </div>
      </div>
      <pre className="json-view">{serialized}</pre>
    </div>
  );
}
