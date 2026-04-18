import { assignRecheck, autoAssign, createRecheck, getOutliers, getReviewAssignments, manualAssign, submitScore } from "./reviews";

vi.mock("./client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn() }
}));

import { apiClient } from "./client";
const mockGet = apiClient.get as ReturnType<typeof vi.fn>;
const mockPost = apiClient.post as ReturnType<typeof vi.fn>;

beforeEach(() => vi.clearAllMocks());

describe("reviews API – getReviewAssignments", () => {
  it("GETs assignments for a round", async () => {
    mockGet.mockResolvedValue({ data: [{ id: 1, reviewer_id: 10, student_id: 20 }] });
    const result = await getReviewAssignments("tok", 5);
    expect(mockGet).toHaveBeenCalledWith("/reviews/rounds/5/assignments", {
      headers: { Authorization: "Bearer tok" }
    });
    expect(result[0].reviewer_id).toBe(10);
  });
});

describe("reviews API – getOutliers", () => {
  it("GETs outliers for a round", async () => {
    mockGet.mockResolvedValue({ data: [{ id: 3, deviation: 2.1, resolved: false }] });
    const result = await getOutliers("tok", 7);
    expect(mockGet).toHaveBeenCalledWith("/reviews/rounds/7/outliers", {
      headers: { Authorization: "Bearer tok" }
    });
    expect(result[0].resolved).toBe(false);
  });
});

describe("reviews API – submitScore", () => {
  it("POSTs to /reviews/scores", async () => {
    const resp = { id: 1, assignment_id: 2, total_score: 4.5, submitted_at: "2026-04-17T00:00:00Z" };
    mockPost.mockResolvedValue({ data: resp });
    const result = await submitScore("tok", { assignment_id: 2, criterion_scores: { Quality: 4.5 } });
    expect(mockPost).toHaveBeenCalledWith(
      "/reviews/scores",
      { assignment_id: 2, criterion_scores: { Quality: 4.5 } },
      { headers: { Authorization: "Bearer tok" } }
    );
    expect(result.total_score).toBe(4.5);
  });
});

describe("reviews API – createRecheck", () => {
  it("POSTs to /reviews/rechecks", async () => {
    mockPost.mockResolvedValue({ data: { id: 10, status: "REQUESTED" } });
    const result = await createRecheck("tok", { round_id: 1, student_id: 5, section_id: 3, reason: "Why?" });
    expect(mockPost).toHaveBeenCalledWith(
      "/reviews/rechecks",
      { round_id: 1, student_id: 5, section_id: 3, reason: "Why?" },
      { headers: { Authorization: "Bearer tok" } }
    );
    expect(result.status).toBe("REQUESTED");
  });
});

describe("reviews API – manualAssign", () => {
  it("POSTs to the manual assignment endpoint", async () => {
    mockPost.mockResolvedValue({ data: { id: 7 } });
    const result = await manualAssign("tok", 3, 11, 22);
    expect(mockPost).toHaveBeenCalledWith(
      "/reviews/rounds/3/assignments/manual",
      { reviewer_id: 11, student_id: 22 },
      { headers: { Authorization: "Bearer tok" } }
    );
    expect(result.id).toBe(7);
  });
});

describe("reviews API – autoAssign", () => {
  it("POSTs to the auto assignment endpoint", async () => {
    mockPost.mockResolvedValue({ data: { created_assignments: 3 } });
    const result = await autoAssign("tok", 4, [10, 11, 12], 1);
    expect(mockPost).toHaveBeenCalledWith(
      "/reviews/rounds/4/assignments/auto",
      { student_ids: [10, 11, 12], reviewers_per_student: 1 },
      { headers: { Authorization: "Bearer tok" } }
    );
    expect(result.created_assignments).toBe(3);
  });
});

describe("reviews API – assignRecheck", () => {
  it("POSTs to /reviews/rechecks/{id}/assign", async () => {
    mockPost.mockResolvedValue({ data: { message: "Assigned." } });
    const result = await assignRecheck("tok", 8, 15);
    expect(mockPost).toHaveBeenCalledWith(
      "/reviews/rechecks/8/assign",
      { reviewer_id: 15 },
      { headers: { Authorization: "Bearer tok" } }
    );
    expect(result.message).toBe("Assigned.");
  });

  it("propagates 404 errors", async () => {
    const err = Object.assign(new Error(), { response: { status: 404 } });
    mockPost.mockRejectedValue(err);
    await expect(assignRecheck("tok", 999, 1)).rejects.toBeDefined();
  });
});
