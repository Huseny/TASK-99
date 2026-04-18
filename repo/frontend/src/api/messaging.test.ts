import { getNotifications, markNotificationRead } from "./messaging";

vi.mock("./client", () => ({
  apiClient: { get: vi.fn(), patch: vi.fn() }
}));

import { apiClient } from "./client";
const mockGet = apiClient.get as ReturnType<typeof vi.fn>;
const mockPatch = (apiClient as unknown as { patch: ReturnType<typeof vi.fn> }).patch;

beforeEach(() => vi.clearAllMocks());

describe("messaging API – getNotifications", () => {
  it("GETs /messaging/notifications with Bearer token", async () => {
    const data = {
      unread_count: 2,
      notifications: [
        { id: 1, title: "Hello", message: "World", read: false, delivered_at: "2026-04-17T00:00:00Z" }
      ]
    };
    mockGet.mockResolvedValue({ data });

    const result = await getNotifications("tok");

    expect(mockGet).toHaveBeenCalledWith("/messaging/notifications", {
      headers: { Authorization: "Bearer tok" }
    });
    expect(result.unread_count).toBe(2);
    expect(result.notifications[0].title).toBe("Hello");
  });

  it("propagates errors", async () => {
    mockGet.mockRejectedValue(new Error("Network error"));
    await expect(getNotifications("tok")).rejects.toThrow("Network error");
  });
});

describe("messaging API – markNotificationRead", () => {
  it("PATCHes /messaging/notifications/{id}/read", async () => {
    mockPatch.mockResolvedValue({ data: { id: 5, read: true } });

    const result = await markNotificationRead("tok", 5);

    expect(mockPatch).toHaveBeenCalledWith(
      "/messaging/notifications/5/read",
      {},
      { headers: { Authorization: "Bearer tok" } }
    );
    expect(result.read).toBe(true);
  });

  it("propagates errors", async () => {
    mockPatch.mockRejectedValue(new Error("Not Found"));
    await expect(markNotificationRead("tok", 999)).rejects.toThrow("Not Found");
  });
});
