import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { StageControlEditor } from "./StageControlEditor";
import type { StageOption } from "../runs/types";

const stages: StageOption[] = [
  { key: "stats", label: "Statistics", enabled: true, mode: "default", modes: ["default"] },
  { key: "pdf_download", label: "PDF Download", enabled: true, mode: "default", modes: ["default", "top-ranked"] }
];

describe("StageControlEditor", () => {
  it("emits stage enabled and mode changes", () => {
    const onChange = vi.fn();
    render(<StageControlEditor stages={stages} onChange={onChange} />);

    fireEvent.click(screen.getByLabelText("Statistics"));
    expect(onChange).toHaveBeenCalledWith([
      { key: "stats", label: "Statistics", enabled: false, mode: "default", modes: ["default"] },
      stages[1]
    ]);

    fireEvent.change(screen.getByLabelText("PDF Download mode"), { target: { value: "top-ranked" } });
    expect(onChange).toHaveBeenCalled();
  });
});
