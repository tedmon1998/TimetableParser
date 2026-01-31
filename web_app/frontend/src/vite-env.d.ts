/// <reference types="vite/client" />

declare module 'xlsx' {
  export function read(data: Uint8Array | ArrayBuffer, opts?: { type: string }): {
    SheetNames: string[];
    Sheets: Record<string, unknown>;
  };
  export const utils: {
    sheet_to_html(ws: unknown, opts?: { id?: string; editable?: boolean }): string;
  };
}
