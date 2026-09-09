import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ReportsPage } from "./ReportsPage";
import { ApiError } from "@/lib/api/client";
import type {
  AdminProfile,
  CustomersReport,
  RidesReport,
} from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  getAdminProfile: vi.fn(),
  getRidesReport: vi.fn(),
  getCustomersReport: vi.fn(),
  getDriversReport: vi.fn(),
  getFinancialReport: vi.fn(),
  getPenaltiesReport: vi.fn(),
  getPromotionsReferralsReport: vi.fn(),
  getSafetySupportReport: vi.fn(),
  getNotificationsReport: vi.fn(),
  getMatchingReport: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/reports",
}));

vi.mock("@/lib/api/dashboard", () => ({
  getAdminProfile: mocks.getAdminProfile,
}));

vi.mock("@/lib/api/reports", () => ({
  getRidesReport: mocks.getRidesReport,
  getCustomersReport: mocks.getCustomersReport,
  getDriversReport: mocks.getDriversReport,
  getFinancialReport: mocks.getFinancialReport,
  getPenaltiesReport: mocks.getPenaltiesReport,
  getPromotionsReferralsReport: mocks.getPromotionsReferralsReport,
  getSafetySupportReport: mocks.getSafetySupportReport,
  getNotificationsReport: mocks.getNotificationsReport,
  getMatchingReport: mocks.getMatchingReport,
}));

const PROFILE: AdminProfile = {
  admin_id: "admin-1",
  role: "SUPER_ADMIN",
  status: "ACTIVE",
  created_at: "2026-08-01T00:00:00Z",
  permissions: [],
};

const RIDES_REPORT: RidesReport = {
  from: "2026-07-29T00:00:00.000Z",
  to: "2026-08-28T00:00:00.000Z",
  rides_by_status: { CLOSED: 10, CANCELLED: 2 },
  rides_by_vehicle_category: { BIKE: 3, AUTO: 4, CAB: 5 },
  average_fare: 123.45,
  completion_rate: 0.8333,
};

const CUSTOMERS_REPORT: CustomersReport = {
  from: "2026-07-29T00:00:00.000Z",
  to: "2026-08-28T00:00:00.000Z",
  total_customers: 500,
  new_customers_in_range: 40,
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getAdminProfile.mockResolvedValue(PROFILE);
});

describe("ReportsPage", () => {
  it("shows a loading state, then the Rides report by default", async () => {
    mocks.getRidesReport.mockResolvedValue(RIDES_REPORT);
    render(<ReportsPage />);

    expect(screen.getByText(/Loading Reports\/Analytics/)).toBeInTheDocument();
    expect(await screen.findByText("Completion rate")).toBeInTheDocument();
    expect(screen.getByText("83.3%")).toBeInTheDocument();
    expect(screen.getByText("₹123.45")).toBeInTheDocument();
    expect(screen.getByText("Rides by status")).toBeInTheDocument();
    expect(screen.getByText("CLOSED")).toBeInTheDocument();
    expect(screen.getByText("10")).toBeInTheDocument();
  });

  it("shows a FORBIDDEN error as an access message", async () => {
    mocks.getRidesReport.mockRejectedValue(
      new ApiError("FORBIDDEN", "no access", 403),
    );
    render(<ReportsPage />);

    expect(
      await screen.findByText(
        "Your admin account does not have access to Reports/Analytics.",
      ),
    ).toBeInTheDocument();
  });

  it("switches to the Customers report and fetches its data", async () => {
    const user = userEvent.setup();
    mocks.getRidesReport.mockResolvedValue(RIDES_REPORT);
    mocks.getCustomersReport.mockResolvedValue(CUSTOMERS_REPORT);
    render(<ReportsPage />);
    await screen.findByText("Completion rate");

    await user.selectOptions(
      screen.getByLabelText("Select report"),
      "customers",
    );

    expect(await screen.findByText("Total customers")).toBeInTheDocument();
    expect(screen.getByText("500")).toBeInTheDocument();
    expect(mocks.getCustomersReport).toHaveBeenCalledWith("", "");
  });

  it("widens plain date inputs to a full-day range before requesting", async () => {
    const user = userEvent.setup();
    mocks.getRidesReport.mockResolvedValue(RIDES_REPORT);
    render(<ReportsPage />);
    await screen.findByText("Completion rate");

    const fromInput = screen.getByLabelText("From date");
    const toInput = screen.getByLabelText("To date");
    await user.type(fromInput, "2026-08-01");
    await user.type(toInput, "2026-08-28");
    await user.click(screen.getByRole("button", { name: "Apply" }));

    expect(mocks.getRidesReport).toHaveBeenLastCalledWith(
      "2026-08-01T00:00:00.000Z",
      "2026-08-28T23:59:59.999Z",
    );
  });
});
