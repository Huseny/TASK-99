import {
  getArrears,
  importReconciliationCsv,
  postDeposit,
  postMonthEndBilling,
  postPayment,
  postPrepayment,
  postRefund,
} from "./finance";

vi.mock("./client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn() }
}));

import { apiClient } from "./client";
const mockGet = apiClient.get as ReturnType<typeof vi.fn>;
const mockPost = apiClient.post as ReturnType<typeof vi.fn>;

beforeEach(() => vi.clearAllMocks());

const BASE_PAYLOAD = {
  student_id: 42,
  amount: 100,
  entry_date: "2026-04-17",
  instrument: "BANK_TRANSFER",
  description: "Test",
};

describe("finance API – getArrears", () => {
  it("GETs /finance/arrears with Bearer token", async () => {
    mockGet.mockResolvedValue({ data: [{ student_id: 1, balance: 200, overdue_days: 15 }] });
    const result = await getArrears("tok");
    expect(mockGet).toHaveBeenCalledWith("/finance/arrears", { headers: { Authorization: "Bearer tok" } });
    expect(result[0].balance).toBe(200);
  });
});

describe("finance API – postPayment", () => {
  it("POSTs to /finance/payments", async () => {
    mockPost.mockResolvedValue({ data: { id: 1, entry_type: "payment", amount: -100 } });
    const result = await postPayment("tok", BASE_PAYLOAD);
    expect(mockPost).toHaveBeenCalledWith("/finance/payments", BASE_PAYLOAD, { headers: { Authorization: "Bearer tok" } });
    expect(result.entry_type).toBe("payment");
  });
});

describe("finance API – postPrepayment", () => {
  it("POSTs to /finance/prepayments", async () => {
    mockPost.mockResolvedValue({ data: { id: 2, entry_type: "payment", amount: -100 } });
    await postPrepayment("tok", BASE_PAYLOAD);
    expect(mockPost).toHaveBeenCalledWith("/finance/prepayments", BASE_PAYLOAD, { headers: { Authorization: "Bearer tok" } });
  });
});

describe("finance API – postDeposit", () => {
  it("POSTs to /finance/deposits", async () => {
    mockPost.mockResolvedValue({ data: { id: 3, entry_type: "payment", amount: -100 } });
    await postDeposit("tok", BASE_PAYLOAD);
    expect(mockPost).toHaveBeenCalledWith("/finance/deposits", BASE_PAYLOAD, { headers: { Authorization: "Bearer tok" } });
  });
});

describe("finance API – postRefund", () => {
  it("POSTs to /finance/refunds with refund-specific shape", async () => {
    const refundPayload = { ...BASE_PAYLOAD, reference_entry_id: 99 };
    mockPost.mockResolvedValue({ data: { id: 4, entry_type: "refund", amount: 100 } });
    await postRefund("tok", refundPayload);
    expect(mockPost).toHaveBeenCalledWith(
      "/finance/refunds",
      {
        student_id: 42,
        amount: 100,
        reference_entry_id: 99,
        description: "Test",
        entry_date: "2026-04-17",
      },
      { headers: { Authorization: "Bearer tok" } }
    );
  });
});

describe("finance API – postMonthEndBilling", () => {
  it("POSTs to /finance/month-end-billing with billing shape", async () => {
    mockPost.mockResolvedValue({ data: { id: 5, entry_type: "charge", amount: 100 } });
    await postMonthEndBilling("tok", BASE_PAYLOAD);
    expect(mockPost).toHaveBeenCalledWith(
      "/finance/month-end-billing",
      {
        student_id: 42,
        amount: 100,
        description: "Test",
        entry_date: "2026-04-17",
      },
      { headers: { Authorization: "Bearer tok" } }
    );
  });
});

describe("finance API – importReconciliationCsv", () => {
  it("POSTs a FormData object to /finance/reconciliation/import", async () => {
    mockPost.mockResolvedValue({ data: { import_id: "abc", matched_total: 500, unmatched_total: 0 } });
    const result = await importReconciliationCsv("tok", "student_id,amount\n1,100\n");
    expect(mockPost).toHaveBeenCalledWith(
      "/finance/reconciliation/import",
      expect.any(FormData),
      { headers: { Authorization: "Bearer tok" } }
    );
    expect(result.import_id).toBe("abc");
  });

  it("propagates errors", async () => {
    mockPost.mockRejectedValue(new Error("CSV error"));
    await expect(importReconciliationCsv("tok", "bad")).rejects.toThrow("CSV error");
  });
});
