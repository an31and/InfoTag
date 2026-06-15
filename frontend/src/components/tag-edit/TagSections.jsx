/**
 * TagEdit sub-components.  Extracted from the original 234-line page so
 * each section is independently understandable + testable.
 */
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import { Switch } from "../ui/switch";
import { Textarea } from "../ui/textarea";

function Field({ label, children }) {
    return (
        <div className="space-y-1.5">
            <Label>{label}</Label>
            {children}
        </div>
    );
}

export function Section({ title, children }) {
    return (
        <section className="surface p-6 space-y-4">
            <h2 className="font-display text-lg font-bold">{title}</h2>
            {children}
        </section>
    );
}

export function TagBasicSection({ tag, set, isNew, t }) {
    return (
        <Section title={t("tag_edit.section_basic")}>
            {isNew && (
                <Field label="Type">
                    <Select value={tag.type} onValueChange={(v) => set("type", v)}>
                        <SelectTrigger data-testid="tag-type-trigger"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            {["vehicle", "pet", "luggage", "keys", "medical", "general"].map((k) => (
                                <SelectItem key={k} value={k}>{t(`dashboard.${k}`)}</SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </Field>
            )}
            <Field label={t("tag_edit.label")}>
                <Input value={tag.label || ""} onChange={(e) => set("label", e.target.value)} placeholder="My Bike" data-testid="tag-label-input" />
            </Field>
            <Field label={t("tag_edit.display_name")}>
                <Input value={tag.display_name || ""} onChange={(e) => set("display_name", e.target.value)} placeholder="Royal Enfield Classic 350" data-testid="tag-displayname-input" />
            </Field>
            <Field label={t("tag_edit.message")}>
                <Textarea
                    value={tag.message || ""}
                    onChange={(e) => set("message", e.target.value)}
                    rows={3}
                    placeholder="If you see this bike parked badly or with lights on, tap below."
                    data-testid="tag-message-input"
                />
            </Field>
            {!isNew && (
                <Field label={t("tag_edit.section_status")}>
                    <Select value={tag.status} onValueChange={(v) => set("status", v)}>
                        <SelectTrigger data-testid="tag-status-trigger"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="active">{t("dashboard.status_active")}</SelectItem>
                            <SelectItem value="lost">{t("dashboard.status_lost")}</SelectItem>
                            <SelectItem value="found">{t("dashboard.status_found")}</SelectItem>
                        </SelectContent>
                    </Select>
                </Field>
            )}
        </Section>
    );
}

export function TagDataSection({ tag, set, fields, t }) {
    if (fields.length === 0) return null;
    return (
        <Section title={t("tag_edit.section_data")}>
            {fields.map((f) => (
                <Field key={f} label={t(`tag_edit.${f}`)}>
                    <Input
                        value={(tag.data && tag.data[f]) || ""}
                        onChange={(e) => set(`data.${f}`, e.target.value)}
                        data-testid={`tag-data-${f}`}
                    />
                </Field>
            ))}
        </Section>
    );
}

export function TagPublicFieldsSection({ tag, set, t }) {
    return (
        <Section title={t("tag_edit.section_public")}>
            <p className="text-sm text-muted-foreground -mt-2 mb-2">
                Toggle off any field you'd like to keep private. Owners' phone numbers are <em>never</em> exposed.
            </p>
            <div className="grid sm:grid-cols-2 gap-3">
                {Object.keys(tag.public_fields || {}).map((key) => (
                    <label key={key} className="flex items-center justify-between p-3 rounded-md border">
                        <span className="text-sm capitalize">{key.replace(/_/g, " ")}</span>
                        <Switch
                            checked={!!tag.public_fields[key]}
                            onCheckedChange={(v) => set(`public_fields.${key}`, v)}
                            data-testid={`public-${key}`}
                        />
                    </label>
                ))}
            </div>
        </Section>
    );
}
