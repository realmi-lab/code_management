import type { HTMLAttributes } from "react";
function icon(name: string) {
  return function SolarIcon(props: HTMLAttributes<HTMLSpanElement>) {
    return <span {...props} aria-hidden="true" style={{ display: "inline-block", background: "currentColor", mask: `url(/workspace-icons/${name}.svg) center / contain no-repeat`, ...props.style }} />;
  };
}
export const LayoutDashboard = icon("widget-2-linear");
export const FileText = icon("document-text-linear");
export const Search = icon("magnifer-linear");
export const Settings = icon("settings-linear");
export const BarChart3 = icon("chart-2-linear");
export const Activity = icon("pulse-2-linear");
