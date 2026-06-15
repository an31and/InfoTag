import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Download } from "lucide-react";

import { API_BASE } from "../lib/api";
import { Button } from "../components/ui/button";
import api, { formatApiError } from "../lib/api";
import { useI18n } from "../lib/i18n";

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
                            alt={`QR for ${tag.display_name}`}
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
                </div>

                <div className="space-y-4">
                    <div className="surface p-6">
                        <h2 className="font-display text-xl font-bold">{t("qr.title")}</h2>
                        <p className="text-sm text-muted-foreground mt-1">{t("qr.tip")}</p>
                        <div className="mt-5 space-y-3">
                            <PdfButton tagId={tag.id} layout="a4_stickers" label={t("qr.download_a4")} testId="dl-a4" />
                            <PdfButton tagId={tag.id} layout="id_card" label={t("qr.download_id")} testId="dl-id" />
                            <PdfButton tagId={tag.id} layout="keyring" label={t("qr.download_keyring")} testId="dl-keyring" />
                        </div>
                    </div>
                </div>
            </div>

            {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
    );
}

function PdfButton({ tagId, layout, label, testId }) {
    const url = `${API_BASE}/tags/${tagId}/pdf?layout=${layout}`;
    const onClick = async (e) => {
        e.preventDefault();
        try {
            // Use fetch so we send the auth cookie
            const res = await fetch(url, { credentials: "include" });
            if (!res.ok) throw new Error("Could not generate PDF");
            const blob = await res.blob();
            const dlUrl = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = dlUrl;
            a.download = `tagit-${layout}.pdf`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(dlUrl);
        } catch (err) {
            alert(err.message);
        }
    };
    return (
        <Button onClick={onClick} variant="outline" className="w-full justify-between rounded-full" data-testid={testId}>
            <span>{label}</span>
            <Download className="h-4 w-4" />
        </Button>
    );
}
