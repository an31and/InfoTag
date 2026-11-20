// Download a credentialed API file (PDF / CSV) as a real "Save as".
// Plain <a download> can't attach the auth cookie cross-origin reliably and
// can't surface API errors, so we fetch → blob → object URL.
import { API_BASE } from "./api";

export async function downloadApiFile(path, filename) {
    const res = await fetch(`${API_BASE}${path}`, { credentials: "include" });
    if (!res.ok) {
        let detail = `Request failed (${res.status})`;
        try {
            const body = await res.json();
            if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
        } catch {
            // non-JSON error body — keep the status text
        }
        throw new Error(detail);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
}

export function toQuery(params) {
    const q = new URLSearchParams();
    Object.entries(params || {}).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== "") q.set(k, typeof v === "boolean" ? (v ? "1" : "0") : String(v));
    });
    const s = q.toString();
    return s ? `?${s}` : "";
}
