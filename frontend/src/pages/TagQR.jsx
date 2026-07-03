import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Check, Copy, Download, Loader2, MessageCircle, QrCode } from "lucide-react";
import { toast } from "sonner";

import { API_BASE } from "../lib/api";
import { Button } from "../components/ui/button";
import api, { formatApiError } from "../lib/api";
import { useI18n } from "../lib/i18n";

/**
 * Stream a credentialed file URL to the user as a download.  We can't use a
 * plain <a download> because the asset endpoints require the auth cookie and
 * need their response turned into a blob to force a real "Save as" rather than
 * a same-tab navigation.
 */
async function downloadFile(url, filename) {
    const res = await fetch(url, { credentials: "include" });
    if (!res.ok) {
        throw new Error(`Request failed (${res.status})`);
    }
    const blob = await res.blob();
    const objectUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = objectUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(objectUrl);
}

export default function TagQRPage() {
    const { id } = useParams();
    const { t } = useI18n();
    const [tag, setTag] = useState(null);
    const [error, setError] = useState("");

    useEffect(() => {
        (async () => {
            try {
                const { data } = await api.get(`/tags/${id}`);
                setTag(data);
            } catch (e) {
                setError(formatApiError(e));
            }
        })();
    }, [id]);

    if (error && !tag) {
        return (
            <div className="max-w-3xl mx-auto" data-testid="qr-root">
                <Link to="/dashboard" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
                    <ArrowLeft className="h-4 w-4" /> {t("common.back")}
                </Link>
                <p className="mt-6 text-sm text-destructive" data-testid="qr-error">{error}</p>
            </div>
        );
    }

    if (!tag) {
        return <div className="text-muted-foreground animate-pulse-soft">{t("common.loading")}</div>;
    }

    const finderUrl = `${window.location.origin}/api/finder/${tag.slug}`;
    const qrSrc = `${API_BASE}/tags/${tag.id}/qr.png`;

    return (
        <div className="max-w-3xl mx-auto space-y-8" data-testid="qr-root">
            <div className="flex items-center gap-3">
                <Link to={`/tags/${id}`} className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground" data-testid="qr-back">
                    <ArrowLeft className="h-4 w-4" /> {t("common.back")}
                </Link>
            </div>

            <div className="grid md:grid-cols-2 gap-6 items-start">
                <div className="surface p-8 flex flex-col items-center text-center">
                    <div className="bg-white p-4 rounded-lg shadow-sm">
                        <img
                            src={qrSrc}
                            alt={`QR for ${tag.display_name || tag.label}`}
                            className="w-56 h-56"
                            data-testid="qr-image"
                            // Ensures we don't show stale caches between tag changes
                            key={tag.id}
                        />
                    </div>
                    <div className="mt-6 font-display text-xl font-bold">{tag.display_name || tag.label}</div>
                    <a
                        href={finderUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="mt-2 font-mono text-xs text-muted-foreground break-all hover:text-accent"
                        data-testid="qr-finder-url"
                    >
                        {finderUrl}
                    </a>
                    <div className="flex flex-wrap items-center justify-center gap-2">
                        <CopyUrlButton url={finderUrl} />
                        <a
                            href={`https://wa.me/?text=${encodeURIComponent(`${t("qr.share_text")} ${finderUrl}`)}`}
                            target="_blank"
                            rel="noreferrer"
                            className="mt-3 inline-flex items-center gap-1.5 rounded-full bg-[#25D366] px-4 py-1.5 text-xs font-semibold text-white hover:opacity-90"
                            data-testid="qr-share-whatsapp"
                        >
                            <MessageCircle className="h-3.5 w-3.5" /> {t("qr.share_whatsapp")}
                        </a>
                    </div>
                </div>

                <div className="space-y-4">
                    <div className="surface p-6">
                        <h2 className="font-display text-xl font-bold">{t("qr.title")}</h2>
                        <p className="text-sm text-muted-foreground mt-1">{t("qr.tip")}</p>
                        <div className="mt-5 space-y-3">
                            <DownloadButton
                                url={`${qrSrc}?download=1`}
                                filename={`info-tag-${tag.slug}-qr.png`}
                                label={t("qr.download_png")}
                                testId="dl-png"
                                icon={QrCode}
                            />
                            <DownloadButton
                                url={`${API_BASE}/tags/${tag.id}/pdf?layout=a4_stickers`}
                                filename={`info-tag-${tag.slug}-a4_stickers.pdf`}
                                label={t("qr.download_a4")}
                                testId="dl-a4"
                            />
                            <DownloadButton
                                url={`${API_BASE}/tags/${tag.id}/pdf?layout=id_card`}
                                filename={`info-tag-${tag.slug}-id_card.pdf`}
                                label={t("qr.download_id")}
                                testId="dl-id"
                            />
                            <DownloadButton
                                url={`${API_BASE}/tags/${tag.id}/pdf?layout=keyring`}
                                filename={`info-tag-${tag.slug}-keyring.pdf`}
                                label={t("qr.download_keyring")}
                                testId="dl-keyring"
                            />
                        </div>
                    </div>
                </div>
            </div>

            {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
    );
}

function DownloadButton({ url, filename, label, testId, icon: Icon = Download }) {
    const { t } = useI18n();
    const [busy, setBusy] = useState(false);

    const onClick = async () => {
        if (busy) return;
        setBusy(true);
        try {
            await downloadFile(url, filename);
            toast.success(t("qr.downloaded"));
        } catch (err) {
            toast.error(t("qr.download_failed"));
            console.error("Download failed:", err);
        } finally {
            setBusy(false);
        }
    };

    return (
        <Button
            onClick={onClick}
            disabled={busy}
            variant="outline"
            className="w-full justify-between rounded-full"
            data-testid={testId}
        >
            <span>{label}</span>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Icon className="h-4 w-4" />}
        </Button>
    );
}

function CopyUrlButton({ url }) {
    const { t } = useI18n();
    const [copied, setCopied] = useState(false);

    const onClick = async () => {
        try {
            await navigator.clipboard.writeText(url);
            setCopied(true);
            toast.success(t("qr.copied"));
            setTimeout(() => setCopied(false), 2000);
        } catch (err) {
            toast.error(t("qr.copy_failed"));
        }
    };

    return (
        <Button
            onClick={onClick}
            variant="ghost"
            size="sm"
            className="mt-3 rounded-full text-xs"
            data-testid="qr-copy-url"
        >
            {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
            <span className="ml-1.5">{copied ? t("qr.copied") : t("qr.copy_url")}</span>
        </Button>
    );
}
