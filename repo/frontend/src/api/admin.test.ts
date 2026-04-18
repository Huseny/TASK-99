import { getAuditLogs, getOrganizations } from "./admin";

vi.mock("./client", () => ({
  apiClient: { get: vi.fn() }
}));

import { apiClient } from "./client";
const mockGet = apiClient.get as ReturnType<typeof vi.fn>;

describe("admin API – getOrganizations", () => {
  beforeEach(() => vi.clearAllMocks());

  it("GETs /admin/organizations with Bearer token", async () => {
    const orgs = [{ id: 1, name: "North Campus", code: "NC", is_active: true }];
    mockGet.mockResolvedValue({ data: orgs });

    const result = await getOrganizations("tok");

    expect(mockGet).toHaveBeenCalledWith("/admin/organizations", {
      headers: { Authorization: "Bearer tok" }
    });
    expect(result).toEqual(orgs);
  });

  it("propagates errors", async () => {
    mockGet.mockRejectedValue(new Error("Network"));
    await expect(getOrganizations("tok")).rejects.toThrow("Network");
  });
});

describe("admin API – getAuditLogs", () => {
  beforeEach(() => vi.clearAllMocks());

  it("GETs /admin/audit-log with limit=10", async () => {
    const logs = [{ id: 1, action: "create", entity_name: "User", created_at: "2026-04-01T00:00:00Z" }];
    mockGet.mockResolvedValue({ data: logs });

    const result = await getAuditLogs("tok");

    expect(mockGet).toHaveBeenCalledWith("/admin/audit-log?limit=10", {
      headers: { Authorization: "Bearer tok" }
    });
    expect(result).toEqual(logs);
  });
});
