import React from "react";

export function Tooltip({ label, children }) {
  return (
    <div className="tooltip-wrapper">
      {children}
      <div className="tooltip-panel" role="tooltip">
        {label}
      </div>
    </div>
  );
}
