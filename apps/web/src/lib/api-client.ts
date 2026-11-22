export type ProductPreview = {
  id: string;
  code: string;
  name: string;
  default_unit_price_yen: number;
  is_active: true;
};
export type ProductPreviewPage = {
  items: ProductPreview[];
  next_cursor: string | null;
};

export class ApiError extends Error {
  readonly kind: "configuration" | "network" | "timeout" | "http" | "response";
  readonly status: number | undefined;
  readonly requestId: string | undefined;
  constructor(kind: ApiError["kind"], status?: number, requestId?: string) {
    super("APIへの接続を確認できませんでした。");
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
    this.requestId = requestId;
  }
}

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function object(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function productPage(value: unknown): value is ProductPreviewPage {
  return (
    object(value) &&
    Array.isArray(value.items) &&
    value.items.length <= 3 &&
    (value.next_cursor === null ||
      (typeof value.next_cursor === "string" &&
        value.next_cursor.length > 0 &&
        value.next_cursor.length <= 4096)) &&
    value.items.every(
      (item) =>
        object(item) &&
        typeof item.id === "string" &&
        uuid.test(item.id) &&
        typeof item.code === "string" &&
        /^[A-Z0-9][A-Z0-9_-]{0,31}$/.test(item.code) &&
        typeof item.name === "string" &&
        item.name.length >= 1 &&
        [...item.name].length <= 100 &&
        /\S/u.test(item.name) &&
        Number.isSafeInteger(item.default_unit_price_yen) &&
        (item.default_unit_price_yen as number) >= 0 &&
        (item.default_unit_price_yen as number) <= 9_999_999 &&
        item.is_active === true,
    )
  );
}

/** Read-only local transport. api.ts is the server-only entry point. */
export function createApiClient(
  base: string | undefined,
  fetcher: typeof fetch = fetch,
  timeoutMs = 5_000,
) {
  let url: URL;
  try {
    if (!base?.trim()) throw new Error();
    url = new URL(base);
    if (
      url.protocol !== "http:" ||
      !["127.0.0.1", "localhost", "[::1]"].includes(url.hostname) ||
      url.username ||
      url.password ||
      url.pathname !== "/" ||
      url.search ||
      url.hash ||
      !Number.isInteger(timeoutMs) ||
      timeoutMs < 1 ||
      timeoutMs > 30_000
    )
      throw new Error();
  } catch {
    throw new ApiError("configuration");
  }

  async function get<T>(
    path: string,
    valid: (value: unknown) => value is T,
  ): Promise<T> {
    const signal = AbortSignal.timeout(timeoutMs);
    let response: Response;
    try {
      response = await fetcher(new URL(path, url), {
        method: "GET",
        headers: { Accept: "application/json" },
        cache: "no-store",
        redirect: "error",
        signal,
      });
    } catch {
      throw new ApiError(signal.aborted ? "timeout" : "network");
    }
    const id = response.headers.get("x-request-id");
    const requestId = id && uuid.test(id) ? id : undefined;
    if (!response.ok) {
      await response.body?.cancel().catch(() => {});
      throw new ApiError("http", response.status, requestId);
    }
    try {
      const contentType = response.headers.get("content-type")?.split(";")[0];
      if (contentType?.trim().toLowerCase() !== "application/json") {
        await response.body?.cancel();
        throw new Error();
      }
      const value: unknown = await response.json();
      if (!valid(value)) throw new Error();
      return value;
    } catch {
      throw new ApiError(
        signal.aborted ? "timeout" : "response",
        response.status,
        requestId,
      );
    }
  }
  return {
    getHealth: () =>
      get(
        "/health",
        (value): value is { status: "ok" } =>
          object(value) && value.status === "ok",
      ),
    getProductPreview: () =>
      get("/products?is_active=true&limit=3", productPage),
  };
}
