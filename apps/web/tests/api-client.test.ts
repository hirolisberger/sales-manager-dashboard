import assert from "node:assert/strict";
import { test } from "node:test";
import { ApiError, createApiClient } from "../src/lib/api-client.ts";

const id = "00000000-0000-4000-8000-000000000001";
const product = {
  id,
  code: "COFFEE",
  name: "コーヒー",
  default_unit_price_yen: 550,
  is_active: true,
};
const base = "http://127.0.0.1:8000";
const respond =
  (value: unknown): typeof fetch =>
  async () =>
    Response.json(value);
const isError = (kind: ApiError["kind"], status?: number) => (error: unknown) =>
  error instanceof ApiError &&
  error.kind === kind &&
  error.status === status &&
  !error.message.includes("PRIVATE");

for (const invalid of [
  undefined,
  "",
  "not-a-url",
  "https://127.0.0.1:8000",
  "http://example.com",
  "http://127.0.0.2:8000",
  "http://user:PRIVATE@127.0.0.1:8000",
  `${base}/prefix`,
  `${base}?token=PRIVATE`,
  `${base}#PRIVATE`,
  "file:///tmp/api",
]) {
  test(
    "reject unapproved API base: " +
      String(invalid).replace("PRIVATE", "redacted"),
    () => {
      assert.throws(() => createApiClient(invalid), isError("configuration"));
    },
  );
}
for (const url of [base, "http://localhost:8000/", "http://[::1]:8000"]) {
  test(`accept local API origin ${url}`, async () => {
    assert.deepEqual(
      await createApiClient(url, respond({ status: "ok" })).getHealth(),
      { status: "ok" },
    );
  });
}
test("health transport is GET, no-store, bounded, redirect rejecting and header minimal", async () => {
  const fetcher: typeof fetch = async (input, init) => {
    assert.equal(String(input), `${base}/health`);
    assert.equal(init?.method, "GET");
    assert.equal(init?.cache, "no-store");
    assert.equal(init?.redirect, "error");
    assert.deepEqual(init?.headers, { Accept: "application/json" });
    assert.ok(init.signal instanceof AbortSignal);
    return Response.json({ status: "ok" });
  };
  await createApiClient(base, fetcher).getHealth();
});
test("product preview always uses active=true and limit=3", async () => {
  const fetcher: typeof fetch = async (input) => {
    assert.equal(String(input), `${base}/products?is_active=true&limit=3`);
    return Response.json({ items: [product], next_cursor: "signed-cursor" });
  };
  const result = await createApiClient(base, fetcher).getProductPreview();
  assert.equal(result.items[0].default_unit_price_yen, 550);
  assert.equal(result.next_cursor, "signed-cursor");
});
test("empty products is a successful response", async () => {
  assert.deepEqual(
    await createApiClient(
      base,
      respond({ items: [], next_cursor: null }),
    ).getProductPreview(),
    { items: [], next_cursor: null },
  );
});
for (const status of [400, 401, 403, 404, 409, 412, 422, 428, 500, 503]) {
  test(`sanitize HTTP ${status} and retain only valid request ID`, async () => {
    const fetcher: typeof fetch = async () =>
      new Response("PRIVATE internal error", {
        status,
        headers: { "x-request-id": id },
      });
    await assert.rejects(
      createApiClient(base, fetcher).getHealth(),
      (error) =>
        isError("http", status)(error) && (error as ApiError).requestId === id,
    );
  });
}
test("discard untrusted request ID text", async () => {
  const fetcher: typeof fetch = async () =>
    new Response("PRIVATE", {
      status: 503,
      headers: { "x-request-id": "PRIVATE" },
    });
  await assert.rejects(
    createApiClient(base, fetcher).getHealth(),
    (error) => error instanceof ApiError && error.requestId === undefined,
  );
});
for (const data of [null, [], {}, { status: "bad" }, { status: true }]) {
  test(`reject malformed health shape ${JSON.stringify(data)}`, async () => {
    await assert.rejects(
      createApiClient(base, respond(data)).getHealth(),
      isError("response", 200),
    );
  });
}
for (const update of [
  { id: "bad" },
  { code: "lowercase" },
  { name: " " },
  { name: "x".repeat(101) },
  { default_unit_price_yen: "550" },
  { default_unit_price_yen: 1.5 },
  { default_unit_price_yen: -1 },
  { default_unit_price_yen: 10_000_000 },
  { is_active: false },
]) {
  test(`reject malformed product ${JSON.stringify(update)}`, async () => {
    await assert.rejects(
      createApiClient(
        base,
        respond({ items: [{ ...product, ...update }], next_cursor: null }),
      ).getProductPreview(),
      isError("response", 200),
    );
  });
}
for (const data of [
  null,
  { items: null, next_cursor: null },
  { items: [] },
  { items: [], next_cursor: "" },
  { items: [product, product, product, product], next_cursor: null },
  { items: [], next_cursor: "x".repeat(4097) },
]) {
  test(`reject malformed product page ${JSON.stringify(data).slice(0, 80)}`, async () => {
    await assert.rejects(
      createApiClient(base, respond(data)).getProductPreview(),
      isError("response", 200),
    );
  });
}
test("accept zero price and 100 Unicode code points", async () => {
  const result = await createApiClient(
    base,
    respond({
      items: [
        { ...product, name: "☕".repeat(100), default_unit_price_yen: 0 },
      ],
      next_cursor: null,
    }),
  ).getProductPreview();
  assert.equal(result.items[0].default_unit_price_yen, 0);
});
for (const response of [
  () =>
    new Response("PRIVATE<html>", { headers: { "content-type": "text/html" } }),
  () =>
    new Response("PRIVATE invalid json", {
      headers: { "content-type": "application/json" },
    }),
]) {
  test("reject non-JSON or broken JSON without leaking body", async () => {
    await assert.rejects(
      createApiClient(base, async () => response()).getHealth(),
      isError("response", 200),
    );
  });
}
test("network errors become a safe failure", async () => {
  const fetcher: typeof fetch = async () => {
    throw new Error("PRIVATE endpoint");
  };
  await assert.rejects(
    createApiClient(base, fetcher).getHealth(),
    isError("network"),
  );
});
test("timeout aborts an in-flight request", async () => {
  const keepAlive = setTimeout(() => {}, 200);
  const fetcher: typeof fetch = async (_input, init) =>
    new Promise((_resolve, reject) => {
      init?.signal?.addEventListener(
        "abort",
        () => reject(new Error("PRIVATE timeout")),
        { once: true },
      );
    });
  try {
    await assert.rejects(
      createApiClient(base, fetcher, 10).getHealth(),
      isError("timeout"),
    );
  } finally {
    clearTimeout(keepAlive);
  }
});
