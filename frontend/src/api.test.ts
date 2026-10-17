import { describe, expect, it } from "vitest";

import { ApiError } from "./api";

describe("ApiError", () => {
  it("preserves the server status and message", () => {
    const error = new ApiError(409, "This item changed; reload and try again.");

    expect(error.status).toBe(409);
    expect(error.message).toContain("reload");
  });
});
