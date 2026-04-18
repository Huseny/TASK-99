import { getQualityReport, getQuarantine } from "./dataQuality";

vi.mock("./client", () => ({
  apiClient: { get: vi.fn() }
}));

import { apiClient } from "./client";
const mockGet = apiClient.get as ReturnType<typeof vi.fn>;

beforeEach(() => vi.clearAllMocks());

describe("dataQuality API – getQuarantine", () => {
  it("GETs /data-quality/quarantine with limit=20", async () => {
    const items = [{ id: 1, entity_type: "AdminCourseWrite", quality_score: 60, status: "open" }];
    mockGet.mockResolvedValue({ data: items });

    const result = await getQuarantine("tok");

    expect(mockGet).toHaveBeenCalledWith("/data-quality/quarantine?limit=20", {
      headers: { Authorization: "Bearer tok" }
    });
    expect(result).toEqual(items);
  });

  it("propagates errors", async () => {
    mockGet.mockRejectedValue(new Error("Forbidden"));
    await expect(getQuarantine("tok")).rejects.toThrow("Forbidden");
  });
});

describe("dataQuality API – getQualityReport", () => {
  it("GETs /data-quality/report", async () => {
    const report = [{ entity_type: "AdminCourseWrite", open_items: 3, avg_quality_score: 72.5 }];
    mockGet.mockResolvedValue({ data: report });

    const result = await getQualityReport("tok");

    expect(mockGet).toHaveBeenCalledWith("/data-quality/report", {
      headers: { Authorization: "Bearer tok" }
    });
    expect(result[0].entity_type).toBe("AdminCourseWrite");
  });
});
