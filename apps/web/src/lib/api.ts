import "server-only";
import { ApiError, createApiClient } from "./api-client";

export type LoadResult<T> =
  | { ok: true; data: T }
  | { ok: false; requestId?: string };

export async function loadApi<T>(
  read: (api: ReturnType<typeof createApiClient>) => Promise<T>,
): Promise<LoadResult<T>> {
  try {
    const api = createApiClient(process.env.API_BASE_URL);
    return { ok: true, data: await read(api) };
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    return { ok: false, requestId: error.requestId };
  }
}
