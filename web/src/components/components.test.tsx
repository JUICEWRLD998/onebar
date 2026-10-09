import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LazyMotion, domAnimation } from "motion/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import examples from "../data/examples.json";
import { finalState } from "../hooks/useAuditSequence";
import type { Message, Trace } from "../lib/types";
import { AuditSheet } from "./audit/AuditSheet";
import { Composer } from "./Composer";
import { PlacePicker } from "./PlacePicker";
import { ReplyBubble } from "./ReplyBubble";

const trace = examples[0] as unknown as Trace; // the ridge example: three numbers, a base-model draft that fails two checks
const wrap = (ui: ReactNode) => (
  <MemoryRouter>
    <LazyMotion features={domAnimation}>{ui}</LazyMotion>
  </MemoryRouter>
);

const message: Message = { id: "r1", role: "reply", text: trace.reply, status: "done", trace };

describe("ReplyBubble", () => {
  const props = (over = {}) => ({
    message,
    selected: true,
    seq: finalState(3, 5),
    active: 0 as number | null,
    onSelect: vi.fn(),
    onActivate: vi.fn(),
    registerToken: vi.fn(),
    ...over,
  });

  it("makes every traced number a button that names its source", () => {
    render(wrap(<ReplyBubble {...props()} />));
    const buttons = screen.getAllByRole("button");
    expect(buttons.map((b) => b.textContent)).toEqual(["15:30", "21:00", "54km/h"]);
    expect(buttons[1]).toHaveAccessibleName(/21:00, first storm hour/);
  });
  it("marks the focused number and tells the parent on hover and focus", async () => {
    const p = props();
    render(wrap(<ReplyBubble {...p} />));
    const [first, second] = screen.getAllByRole("button");
    expect(first).toHaveAttribute("data-state", "active");
    expect(second).toHaveAttribute("data-state", "verified");
    await userEvent.hover(second!);
    expect(p.onActivate).toHaveBeenCalledWith(1);
    fireEvent.focus(first!);
    expect(p.onActivate).toHaveBeenCalledWith(0);
  });
  it("shows numbers not yet checked as pending, in order", () => {
    render(wrap(<ReplyBubble {...props({ seq: { ...finalState(3, 5), verified: 1, active: 0, done: false } })} />));
    expect(screen.getAllByRole("button").map((b) => b.dataset.state)).toEqual(["active", "pending", "pending"]);
  });
  it("keeps the full text, punctuation included", () => {
    render(wrap(<ReplyBubble {...props()} />));
    expect(screen.getByText(/Yes, ridge ok by/).closest("div")).toHaveTextContent(trace.reply);
  });
  it("offers to reopen the check for a reply that is not on the sheet, and has no number buttons", async () => {
    const onSelect = vi.fn();
    render(wrap(<ReplyBubble {...props({ selected: false, onSelect })} />));
    expect(screen.queryByRole("button", { name: /15:30/ })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Show how this was checked" }));
    expect(onSelect).toHaveBeenCalled();
  });
  it("labels a recorded example as not live", () => {
    render(wrap(<ReplyBubble {...props({ message: { ...message, recorded: true } })} />));
    expect(screen.getByText(/Recorded example from the test set. Not live./)).toBeInTheDocument();
  });
});

describe("Composer", () => {
  it("cannot send nothing, or while a reply is on its way", () => {
    const { rerender } = render(<Composer onSend={vi.fn()} busy={false} showExamples={false} />);
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    rerender(<Composer onSend={vi.fn()} busy={true} showExamples={false} />);
    fireEvent.change(screen.getByLabelText("Your question"), { target: { value: "storm?" } });
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });
  it("sends the trimmed text once and clears the box", async () => {
    const onSend = vi.fn();
    render(<Composer onSend={onSend} busy={false} showExamples={false} />);
    await userEvent.type(screen.getByLabelText("Your question"), "  storm before 3?  {Enter}");
    expect(onSend).toHaveBeenCalledTimes(1);
    expect(onSend).toHaveBeenCalledWith("storm before 3?");
    expect(screen.getByLabelText("Your question")).toHaveValue("");
  });
  it("sends an example question with one tap", async () => {
    const onSend = vi.fn();
    render(<Composer onSend={onSend} busy={false} showExamples={true} />);
    await userEvent.click(screen.getByRole("button", { name: "storm before 3?" }));
    expect(onSend).toHaveBeenCalledWith("storm before 3?");
  });
  it("shows no examples once the thread has started, and a counter near the limit", () => {
    render(<Composer onSend={vi.fn()} busy={false} showExamples={false} />);
    expect(screen.queryByRole("group", { name: "Example questions" })).toBeNull();
    const input = screen.getByLabelText("Your question");
    expect(input).toHaveAttribute("maxlength", "500");
    expect(screen.queryByText(/of 500/)).toBeNull();
    fireEvent.change(input, { target: { value: "x".repeat(450) } });
    expect(screen.getByText("450 of 500")).toBeInTheDocument();
  });
});

describe("PlacePicker", () => {
  const setup = (onSubmit = vi.fn().mockResolvedValue({ ok: true, text: "Place set: Zermatt, Switzerland. Ask your question." })) => {
    const handlers = { onSubmit, onReplay: vi.fn(), onClose: vi.fn() };
    render(<PlacePicker current={null} {...handlers} />);
    return handlers;
  };

  it("sets a typed place and closes when the server accepts it", async () => {
    const h = setup();
    await userEvent.type(screen.getByLabelText("Place name"), "Zermatt{Enter}");
    await waitFor(() => expect(h.onClose).toHaveBeenCalled());
    expect(h.onSubmit).toHaveBeenCalledWith("Zermatt");
  });
  it("says what to try when the place is not found, and stays open", async () => {
    const h = setup(vi.fn().mockResolvedValue({ ok: false, text: "Could not find Xyzzy. Send PLACE with a town or a peak." }));
    await userEvent.type(screen.getByLabelText("Place name"), "Xyzzy{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent(/Try a larger town nearby, or type coordinates/);
    expect(h.onClose).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Place name")).toHaveAttribute("aria-invalid", "true");
  });
  it("sets a quick place with one tap", async () => {
    const h = setup();
    await userEvent.click(screen.getByRole("button", { name: "Snowdon" }));
    expect(h.onSubmit).toHaveBeenCalledWith("Snowdon");
  });
  it("replays a recorded example without a place", async () => {
    const h = setup();
    await userEvent.click(screen.getByRole("button", { name: trace.question }));
    expect(h.onReplay).toHaveBeenCalledWith(expect.objectContaining({ id: trace.id }));
    expect(h.onClose).toHaveBeenCalled();
    expect(h.onSubmit).not.toHaveBeenCalled();
  });
  it("offers a way back when a place is already set", () => {
    render(<PlacePicker current="Banff" onSubmit={vi.fn()} onReplay={vi.fn()} onClose={vi.fn()} />);
    expect(screen.getByRole("heading", { name: "Change your place" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Keep Banff" })).toBeInTheDocument();
  });
});

describe("AuditSheet", () => {
  const sheet = (over = {}) => ({
    trace,
    model: "tuned" as const,
    onModel: vi.fn(),
    seq: finalState(3, 5),
    active: 0 as number | null,
    onActivate: vi.fn(),
    registerRow: vi.fn(),
    ...over,
  });

  it("shows the verdict, a row per number and all five checks for the tuned reply", () => {
    render(wrap(<AuditSheet {...sheet()} />));
    expect(screen.getByText("Checked. 3 of 3 numbers traced to the forecast. 65 of 160 characters.")).toBeInTheDocument();
    expect(screen.getByText("first storm hour")).toBeInTheDocument();
    expect(screen.getAllByText(/Under 160 characters|Plain SMS characters|Every number traced|Says what the question needs|Agrees with the forecast/)).toHaveLength(5);
  });
  it("switches to the base model and shows what it failed", async () => {
    const onModel = vi.fn();
    const { rerender } = render(wrap(<AuditSheet {...sheet({ onModel })} />));
    await userEvent.click(screen.getByRole("button", { name: "Base model" }));
    expect(onModel).toHaveBeenCalledWith("base");
    rerender(wrap(<AuditSheet {...sheet({ onModel, model: "base" })} />));
    expect(screen.getByText("Base model draft")).toBeInTheDocument();
    expect(screen.getAllByText("Not sent. 2 checks failed.").length).toBeGreaterThan(0);
    expect(screen.getByText(/81 over the 160 limit/)).toBeInTheDocument();
  });
  it("disables the base model button when no draft was recorded", () => {
    render(wrap(<AuditSheet {...sheet({ trace: { ...trace, baseline: null } })} />));
    expect(screen.getByRole("button", { name: "Base model" })).toBeDisabled();
  });
  it("reports a number with no source as untraced, in words", () => {
    const bad: Trace = { ...trace, numbers: [{ text: "99%", ok: false, sources: [] }], reply: "Rain 99%." };
    render(wrap(<AuditSheet {...sheet({ trace: bad, seq: finalState(1, 5) })} />));
    expect(screen.getByText("Not in the forecast or your question")).toBeInTheDocument();
  });
  it("hovering a row tells the parent which number is in focus", async () => {
    const onActivate = vi.fn();
    render(wrap(<AuditSheet {...sheet({ onActivate })} />));
    await userEvent.hover(screen.getByText("strongest gust").closest("li")!);
    expect(onActivate).toHaveBeenCalledWith(2);
  });
  it("labels a sample as a recorded example and offers no permalink", () => {
    render(wrap(<AuditSheet {...sheet({ sample: true, traceId: "abc" })} />));
    expect(screen.getByRole("heading", { name: "A recorded example, checked" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /own page/ })).toBeNull();
  });
  it("links a live reply to its own page", () => {
    render(wrap(<AuditSheet {...sheet({ traceId: "a/b" })} />));
    expect(screen.getByRole("link", { name: /own page/ })).toHaveAttribute("href", "/trace/a%2Fb");
  });
});
