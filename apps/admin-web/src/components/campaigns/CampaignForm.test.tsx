import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CampaignForm } from "./CampaignForm";
import type { Campaign } from "@/lib/api/types";

const CAMPAIGN: Campaign = {
  campaign_id: "campaign-1",
  code: "SAVE50",
  name: "50% off launch week",
  vehicle_category: "CAB",
  discount_type: "PERCENT",
  discount_value: 50,
  max_discount_amount: 100,
  minimum_fare: null,
  eligible_scope: "ALL",
  per_customer_use_limit: 1,
  total_usage_limit: null,
  ride_count_limit: null,
  starts_at: "2026-08-10T09:00:00.000Z",
  ends_at: null,
  status: "DRAFT",
  created_by: "admin-1",
  created_at: "2026-08-10T00:00:00Z",
};

describe("CampaignForm", () => {
  it("disables submit until name, discount value, and starts_at are set", () => {
    render(
      <CampaignForm submitLabel="Create draft" onSubmit={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(
      screen.getByRole("button", { name: "Create draft" }),
    ).toBeDisabled();
  });

  it("pre-fills every field from `initial` for editing", () => {
    render(
      <CampaignForm
        initial={CAMPAIGN}
        submitLabel="Save changes"
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByLabelText("Name")).toHaveValue("50% off launch week");
    expect(screen.getByLabelText(/Code/)).toHaveValue("SAVE50");
    expect(screen.getByLabelText(/Discount value/)).toHaveValue(50);
    expect(screen.getByLabelText(/Max discount amount/)).toHaveValue(100);
  });

  it("only shows the eligible-customer-IDs field when scope is SELECTED", async () => {
    const user = userEvent.setup();
    render(
      <CampaignForm submitLabel="Create draft" onSubmit={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(
      screen.queryByLabelText(/Eligible customer IDs/),
    ).not.toBeInTheDocument();

    await user.selectOptions(
      screen.getByLabelText("Eligible scope"),
      "SELECTED",
    );

    expect(
      screen.getByLabelText(/Eligible customer IDs/),
    ).toBeInTheDocument();
  });

  it("submits a well-formed request, parsing eligible_customer_ids from the textarea", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(
      <CampaignForm submitLabel="Create draft" onSubmit={onSubmit} onCancel={vi.fn()} />,
    );

    await user.type(screen.getByLabelText("Name"), "Launch offer");
    await user.type(screen.getByLabelText(/Discount value/), "25");
    await user.type(screen.getByLabelText("Starts at"), "2026-09-01T00:00");
    await user.selectOptions(
      screen.getByLabelText("Eligible scope"),
      "SELECTED",
    );
    await user.type(
      screen.getByLabelText(/Eligible customer IDs/),
      "cust-1, cust-2\ncust-3",
    );
    await user.click(screen.getByRole("button", { name: "Create draft" }));

    expect(onSubmit).toHaveBeenCalledTimes(1);
    const body = onSubmit.mock.calls[0][0];
    expect(body.name).toBe("Launch offer");
    expect(body.discount_value).toBe(25);
    expect(body.eligible_scope).toBe("SELECTED");
    expect(body.eligible_customer_ids).toEqual(["cust-1", "cust-2", "cust-3"]);
    expect(body.code).toBeNull();
  });

  it("calls onCancel when Cancel is clicked", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    render(
      <CampaignForm submitLabel="Create draft" onSubmit={vi.fn()} onCancel={onCancel} />,
    );

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalled();
  });
});
