export function extractApiErrorMessage(err: unknown, fallback = "An unexpected error occurred"): string {
  const axiosErr = err as { response?: { data?: { detail?: string } } };
  return axiosErr?.response?.data?.detail || (err instanceof Error ? err.message : fallback);
}
