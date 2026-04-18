import {
  dropSection,
  enrollInSection,
  getCourseDetail,
  getCourses,
  getEligibility,
  getRegistrationHistory,
  getRegistrationStatus,
  joinWaitlist,
} from "./registration";

vi.mock("./client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn() }
}));

import { apiClient } from "./client";
const mockGet = apiClient.get as ReturnType<typeof vi.fn>;
const mockPost = apiClient.post as ReturnType<typeof vi.fn>;

beforeEach(() => vi.clearAllMocks());

describe("registration API – getCourses", () => {
  it("GETs /courses with Bearer token", async () => {
    mockGet.mockResolvedValue({ data: [{ id: 1, code: "CS101", title: "Intro", credits: 3, available_seats: 5 }] });
    const result = await getCourses("tok");
    expect(mockGet).toHaveBeenCalledWith("/courses", { headers: { Authorization: "Bearer tok" } });
    expect(result[0].code).toBe("CS101");
  });
});

describe("registration API – getCourseDetail", () => {
  it("GETs /courses/{id}", async () => {
    mockGet.mockResolvedValue({ data: { id: 1, code: "CS101", title: "Intro", credits: 3, prerequisites: [], sections: [] } });
    const result = await getCourseDetail("tok", 1);
    expect(mockGet).toHaveBeenCalledWith("/courses/1", { headers: { Authorization: "Bearer tok" } });
    expect(result.sections).toEqual([]);
  });
});

describe("registration API – getEligibility", () => {
  it("GETs eligibility endpoint", async () => {
    mockGet.mockResolvedValue({ data: { eligible: true, reasons: [] } });
    const result = await getEligibility("tok", 1, 2);
    expect(mockGet).toHaveBeenCalledWith("/courses/1/sections/2/eligibility", {
      headers: { Authorization: "Bearer tok" }
    });
    expect(result.eligible).toBe(true);
  });
});

describe("registration API – getRegistrationStatus", () => {
  it("GETs /registration/status", async () => {
    mockGet.mockResolvedValue({ data: [{ section_id: 3, course_code: "CS101", status: "enrolled" }] });
    const result = await getRegistrationStatus("tok");
    expect(mockGet).toHaveBeenCalledWith("/registration/status", { headers: { Authorization: "Bearer tok" } });
    expect(result[0].status).toBe("enrolled");
  });
});

describe("registration API – getRegistrationHistory", () => {
  it("GETs /registration/history", async () => {
    mockGet.mockResolvedValue({ data: [{ id: 1, event_type: "enrolled", details: null, created_at: "2026-04-01T00:00:00Z" }] });
    const result = await getRegistrationHistory("tok");
    expect(mockGet).toHaveBeenCalledWith("/registration/history", { headers: { Authorization: "Bearer tok" } });
    expect(result[0].event_type).toBe("enrolled");
  });
});

describe("registration API – enrollInSection", () => {
  it("POSTs to /registration/enroll with idempotency key", async () => {
    mockPost.mockResolvedValue({ data: { status: "enrolled", section_id: 5 } });
    const result = await enrollInSection("tok", 5);
    expect(mockPost).toHaveBeenCalledWith(
      "/registration/enroll",
      { section_id: 5 },
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer tok",
          "Idempotency-Key": expect.any(String)
        })
      })
    );
    expect(result.status).toBe("enrolled");
  });
});

describe("registration API – joinWaitlist", () => {
  it("POSTs to /registration/waitlist", async () => {
    mockPost.mockResolvedValue({ data: { status: "waitlisted", section_id: 5, priority: 3 } });
    const result = await joinWaitlist("tok", 5);
    expect(mockPost).toHaveBeenCalledWith(
      "/registration/waitlist",
      { section_id: 5 },
      { headers: { Authorization: "Bearer tok" } }
    );
    expect(result.status).toBe("waitlisted");
  });
});

describe("registration API – dropSection", () => {
  it("POSTs to /registration/drop with idempotency key", async () => {
    mockPost.mockResolvedValue({ data: { status: "dropped", section_id: 5 } });
    const result = await dropSection("tok", 5);
    expect(mockPost).toHaveBeenCalledWith(
      "/registration/drop",
      { section_id: 5 },
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer tok" })
      })
    );
    expect(result.status).toBe("dropped");
  });
});
