/**
 * Settings sub-components.  Extracted from the 131-line SettingsPage.
 */
import { Download, Trash2 } from "lucide-react";

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
