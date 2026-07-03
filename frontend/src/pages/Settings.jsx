import { useEffect, useState } from "react";
import { toast } from "sonner";

import {
    ContactSection,
    DataPrivacySection,
    LanguageSection,
    NotificationsSection,
    ProfileSection,
    PushSection,
} from "../components/settings/SettingsParts";
import api, { formatApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useI18n } from "../lib/i18n";

export default function SettingsPage() {
    const { t, lang, setLang, langs } = useI18n();
    const { user, refresh, logout } = useAuth();
    const [me, setMe] = useState(user || null);
    const [error, setError] = useState("");

    useEffect(() => {
        setMe(user);
    }, [user]);

    if (!me) {
        return <div className="text-muted-foreground animate-pulse-soft">{t("common.loading")}</div>;
    }

    const save = async (patch) => {
        try {
            const { data } = await api.patch("/auth/me", patch);
            setMe(data);
            await refresh();
            toast.success(t("settings.saved"));
        } catch (e) {
            setError(formatApiError(e));
        }
    };

    const onExport = async () => {
        try {
            const { data } = await api.get("/auth/export");
            const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = "infotag-export.json";
            a.click();
            URL.revokeObjectURL(url);
        } catch (e) {
            setError(formatApiError(e));
        }
    };

    const onDelete = async () => {
        try {
            await api.delete("/auth/me");
            await logout();
            window.location.href = "/";
        } catch (e) {
            setError(formatApiError(e));
        }
    };

    return (
        <div className="max-w-3xl mx-auto space-y-6" data-testid="settings-root">
            <h1 className="font-display text-3xl font-black tracking-tight">{t("settings.title")}</h1>
            <ProfileSection me={me} setMe={setMe} save={save} t={t} />
            <ContactSection me={me} setMe={setMe} save={save} t={t} />
            <PushSection t={t} />
            <NotificationsSection me={me} save={save} t={t} />
            <LanguageSection lang={lang} setLang={setLang} langs={langs} save={save} t={t} />
            <DataPrivacySection onExport={onExport} onDelete={onDelete} t={t} />
            {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
    );
}
