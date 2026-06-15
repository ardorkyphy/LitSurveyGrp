import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RunLauncherForm } from "./RunLauncherForm";
import { runsApi } from "../runs/api";
import type { JournalOption, StageOption } from "../runs/types";

vi.mock("../runs/api", () => ({
  runsApi: {
    create: vi.fn()
  }
}));

const stages: StageOption[] = [
  { key: "stats", label: "Statistics", enabled: true, mode: "default", modes: ["default"] }
];

const journals: JournalOption[] = [
  { key: "nature-aging", name: "Nature Aging", provider: "layered", group: "nature", issn: "2662-8465" }
];

describe("RunLauncherForm", () => {
  it("submits a typed run request", async () => {
    vi.mocked(runsApi.create).mockResolvedValue({ id: "run_a", path: "run_a", pid: 1, command: [] });
    const onCreated = vi.fn();
    render(<RunLauncherForm stages={stages} journals={journals} onCreated={onCreated} />);

    fireEvent.change(screen.getByLabelText("Output"), { target: { value: "run_a" } });
    fireEvent.change(screen.getByLabelText("Keywords"), { target: { value: "wearable, aging" } });
    fireEvent.click(screen.getByText("Start"));

    await waitFor(() => expect(runsApi.create).toHaveBeenCalled());
    expect(runsApi.create).toHaveBeenCalledWith(expect.objectContaining({
      out: "run_a",
      keyword: ["wearable", "aging"],
      stage_control: expect.objectContaining({
        stats: expect.objectContaining({ enabled: true })
      })
    }));
    expect(onCreated).toHaveBeenCalledWith("run_a");
  });
});

