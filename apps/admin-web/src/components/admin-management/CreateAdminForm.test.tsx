import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CreateAdminForm } from "./CreateAdminForm";
import { ApiError } from "@/lib/api/client";

describe("CreateAdminForm", () => {
  it("submits the entered phone number with no permissions by default", async () => {
    const user = userEvent.setup();
    const onCreate = vi.fn().mockResolvedValue(undefined);
    render(<CreateAdminForm onCreate={onCreate} onCancel={() => {}} />);

    await user.type(
      screen.getByLabelText("Phone number"),
      "+919876543210",
    );
    await user.click(screen.getByRole("button", { name: "Create admin" }));

    await waitFor(() => {
      expect(onCreate).toHaveBeenCalledWith("+919876543210", []);
    });
  });

  it("disables the submit button while the phone field is empty", () => {
    render(<CreateAdminForm onCreate={vi.fn()} onCancel={() => {}} />);
    expect(screen.getByRole("button", { name: "Create admin" })).toBeDisabled();
  });

  it("shows the backend's own error message on failure and does not close the form", async () => {
    const user = userEvent.setup();
    const onCreate = vi
      .fn()
      .mockRejectedValue(
        new ApiError(
          "VALIDATION_FAILED",
          "+919876543210 already has an admin.users row.",
          400,
        ),
      );
    render(<CreateAdminForm onCreate={onCreate} onCancel={() => {}} />);

    await user.type(screen.getByLabelText("Phone number"), "+919876543210");
    await user.click(screen.getByRole("button", { name: "Create admin" }));

    expect(
      await screen.findByText("+919876543210 already has an admin.users row."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Phone number")).toBeInTheDocument();
  });

  it("calls onCancel when Cancel is clicked", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    render(<CreateAdminForm onCreate={vi.fn()} onCancel={onCancel} />);

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalled();
  });
});
