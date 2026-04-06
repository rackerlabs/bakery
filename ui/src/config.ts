export type UiRuntimeConfig = {
  publicUrl: string;
  apiBaseUrl: string;
};

declare global {
  interface Window {
    __BAKERY_UI_CONFIG__?: Partial<UiRuntimeConfig>;
  }
}

function normalizeUrl(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) {
    return "";
  }
  return trimmed.replace(/\/+$/, "");
}

function getRuntimeConfig(): UiRuntimeConfig {
  return {
    publicUrl: normalizeUrl(String(window.__BAKERY_UI_CONFIG__?.publicUrl ?? "")),
    apiBaseUrl: normalizeUrl(String(window.__BAKERY_UI_CONFIG__?.apiBaseUrl ?? "")),
  };
}

function withQueryParams(base: string, params: Record<string, string>): string {
  const runtimeConfig = getRuntimeConfig();
  const url = runtimeConfig.apiBaseUrl ? new URL(base) : new URL(base, window.location.origin);
  for (const [key, value] of Object.entries(params)) {
    url.searchParams.set(key, value);
  }
  if (runtimeConfig.apiBaseUrl) {
    return url.toString();
  }
  return `${url.pathname}${url.search}${url.hash}`;
}

export function usesExternalApiBaseUrl(): boolean {
  return getRuntimeConfig().apiBaseUrl.length > 0;
}

export function buildApiUrl(path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const runtimeConfig = getRuntimeConfig();
  if (!runtimeConfig.apiBaseUrl) {
    return normalizedPath;
  }
  return new URL(normalizedPath, `${runtimeConfig.apiBaseUrl}/`).toString();
}

export function buildAuthHref(path: string, params: Record<string, string>): string {
  return withQueryParams(buildApiUrl(path), params);
}

export function buildLoginReturnTarget(): string {
  const runtimeConfig = getRuntimeConfig();
  return runtimeConfig.publicUrl || "/";
}
