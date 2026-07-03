/**
 * Settings sub-components.  Extracted from the 131-line SettingsPage.
 */
import { useEffect, useState } from "react";
import { Bell, BellRing, Download, MessageSquare, Phone, Trash2 } from "lucide-react";
import { toast } from "sonner";

import api from "../../lib/api";

import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
    AlertDialogTrigger,
} from "../ui/alert-dialog";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import { Switch } from "../ui/switch";

function Row({ label, children }) {
    return (
        <div className="flex items-center justify-between gap-4 p-3 rounded-md border">
            <span className="text-sm">{label}</span>
            {children}
        </div>
    );
}

export function ProfileSection({ me, setMe, save, t }) {
    return (
        <section className="surface p-6 space-y-4">
            <h2 className="font-display text-lg font-bold">{t("settings.account")}</h2>
            <div className="grid sm:grid-cols-2 gap-4">
                <div className="space-y-1.5">
                    <Label>{t("auth.email")}</Label>
                    <Input value={me.email} disabled />
                </div>
                <div className="space-y-1.5">
                    <Label>{t("auth.display_name")}</Label>
                    <Input
                        value={me.display_name || ""}
                        onChange={(e) => setMe({ ...me, display_name: e.target.value })}
                        onBlur={() => save({ display_name: me.display_name })}
                        data-testid="settings-displayname"
                    />
                </div>
            </div>
        </section>
    );
}

export function ContactSection({ me, setMe, save, t }) {
    return (
        <section className="surface p-6 space-y-3">
            <h2 className="font-display text-lg font-bold">{t("settings.contact")}</h2>
            <div className="space-y-1.5">
                <Label>{t("settings.phone_label")}</Label>
                <Input
                    type="tel"
                    placeholder="+91 98765 43210"
                    value={me.phone || ""}
                    onChange={(e) => setMe({ ...me, phone: e.target.value })}
                    onBlur={() => save({ phone: me.phone || "" })}
                    data-testid="settings-phone"
                />
                <p className="text-xs text-muted-foreground">{t("settings.phone_help")}</p>
            </div>
            <Row
                label={
                    <span className="inline-flex items-center gap-2">
                        <MessageSquare className="h-4 w-4 text-emerald-500" /> {t("settings.whatsapp_alerts")}
                    </span>
                }
            >
                <Switch
                    checked={!!me.whatsapp_alerts}
                    onCheckedChange={(v) => save({ whatsapp_alerts: v })}
                    data-testid="whatsapp-alerts-switch"
                />
            </Row>
            <Row
                label={
                    <span className="inline-flex items-center gap-2">
                        <Phone className="h-4 w-4 text-sky-500" /> {t("settings.sms_alerts")}
                    </span>
                }
            >
                <Switch
                    checked={!!me.sms_alerts}
                    onCheckedChange={(v) => save({ sms_alerts: v })}
                    data-testid="sms-alerts-switch"
                />
            </Row>
            <p className="text-xs text-muted-foreground">{t("settings.alerts_note")}</p>
        </section>
    );
}

/* ------------------------------------------------------------------ */
/* Web Push — free phone notifications, no provider needed             */
/* ------------------------------------------------------------------ */
function urlBase64ToUint8Array(base64String) {
    const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
    const raw = window.atob(base64);
    return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

export function PushSection({ t }) {
    const supported = typeof window !== "undefined" && "serviceWorker" in navigator && "PushManager" in window;
    const [serverKey, setServerKey] = useState(null); // null=loading, ""=disabled
    const [subscribed, setSubscribed] = useState(false);
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        if (!supported) return;
        api.get("/push/public-key")
            .then(({ data }) => setServerKey(data.enabled ? data.public_key : ""))
            .catch(() => setServerKey(""));
        navigator.serviceWorker.ready
            .then((reg) => reg.pushManager.getSubscription())
            .then((sub) => setSubscribed(!!sub))
            .catch(() => {});
    }, [supported]);

    const enable = async () => {
        setBusy(true);
        try {
            const perm = await Notification.requestPermission();
            if (perm !== "granted") {
                toast.error(t("settings.push_denied"));
                return;
            }
            const reg = await navigator.serviceWorker.ready;
            const sub = await reg.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: urlBase64ToUint8Array(serverKey),
            });
            await api.post("/push/subscribe", { subscription: sub.toJSON() });
            setSubscribed(true);
            toast.success(t("settings.push_enabled"));
            api.post("/push/test").catch(() => {});
        } catch {
            toast.error(t("settings.push_failed"));
        } finally {
            setBusy(false);
        }
    };

    const disable = async () => {
        setBusy(true);
        try {
            const reg = await navigator.serviceWorker.ready;
            const sub = await reg.pushManager.getSubscription();
            if (sub) {
                await api.post("/push/unsubscribe", { subscription: sub.toJSON() }).catch(() => {});
                await sub.unsubscribe();
            }
            setSubscribed(false);
            toast.success(t("settings.push_disabled"));
        } catch {
            toast.error(t("settings.push_failed"));
        } finally {
            setBusy(false);
        }
    };

    return (
        <section className="surface p-6 space-y-3" data-testid="push-section">
            <h2 className="font-display text-lg font-bold flex items-center gap-2">
                <BellRing className="h-5 w-5 text-accent" /> {t("settings.push_title")}
            </h2>
            <p className="text-sm text-muted-foreground">{t("settings.push_help")}</p>
            {!supported && <p className="text-sm text-amber-600 dark:text-amber-400">{t("settings.push_unsupported")}</p>}
            {supported && serverKey === "" && (
                <p className="text-sm text-amber-600 dark:text-amber-400">{t("settings.push_not_configured")}</p>
            )}
            {supported && serverKey && (
                <Button
                    variant={subscribed ? "outline" : "default"}
                    disabled={busy}
                    onClick={subscribed ? disable : enable}
                    className="gap-2 rounded-full"
                    data-testid="push-toggle-btn"
                >
                    <Bell className="h-4 w-4" />
                    {subscribed ? t("settings.push_turn_off") : t("settings.push_turn_on")}
                </Button>
            )}
        </section>
    );
}

export function NotificationsSection({ me, save, t }) {
    return (
        <section className="surface p-6 space-y-3">
            <h2 className="font-display text-lg font-bold">{t("settings.notifications")}</h2>
            <Row label={t("settings.notify_on_message")}>
                <Switch
                    checked={!!me.notify_on_message}
                    onCheckedChange={(v) => save({ notify_on_message: v })}
                    data-testid="notify-message-switch"
                />
            </Row>
            <Row label={t("settings.notify_on_scan")}>
                <Switch
                    checked={!!me.notify_on_scan}
                    onCheckedChange={(v) => save({ notify_on_scan: v })}
                    data-testid="notify-scan-switch"
                />
            </Row>
        </section>
    );
}

export function LanguageSection({ lang, setLang, langs, save, t }) {
    return (
        <section className="surface p-6 space-y-3">
            <h2 className="font-display text-lg font-bold">{t("settings.language")}</h2>
            <Select value={lang} onValueChange={(v) => { setLang(v); save({ locale: v }); }}>
                <SelectTrigger data-testid="settings-lang-trigger"><SelectValue /></SelectTrigger>
                <SelectContent>
                    {langs.map((l) => (
                        <SelectItem key={l.code} value={l.code}>{l.label}</SelectItem>
                    ))}
                </SelectContent>
            </Select>
        </section>
    );
}

export function DataPrivacySection({ onExport, onDelete, t }) {
    return (
        <section className="surface p-6 space-y-3">
            <h2 className="font-display text-lg font-bold">Data & privacy</h2>
            <Button variant="outline" onClick={onExport} className="gap-2" data-testid="export-data-btn">
                <Download className="h-4 w-4" /> {t("settings.export")}
            </Button>
            <AlertDialog>
                <AlertDialogTrigger asChild>
                    <Button variant="ghost" className="text-destructive gap-2" data-testid="delete-account-btn">
                        <Trash2 className="h-4 w-4" /> {t("settings.delete_account")}
                    </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>{t("settings.delete_account")}</AlertDialogTitle>
                        <AlertDialogDescription>{t("settings.delete_warning")}</AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel data-testid="delete-account-cancel">{t("common.cancel")}</AlertDialogCancel>
                        <AlertDialogAction onClick={onDelete} data-testid="delete-account-confirm">{t("settings.confirm_delete")}</AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </section>
    );
}
