import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, HeartPulse, Save, Trash2 } from "lucide-react";

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
} from "../components/ui/alert-dialog";
import { Button } from "../components/ui/button";
import { toast } from "sonner";

import {
    TagBasicSection,
    TagContactSection,
    TagDataSection,
    TagPublicFieldsSection,
} from "../components/tag-edit/TagSections";
import api, { formatApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useI18n } from "../lib/i18n";

const TYPE_FIELDS = {
    vehicle: ["vehicle_make_model", "vehicle_plate", "reward"],
    pet: ["pet_name", "pet_breed", "note", "reward"],
    luggage: ["note", "reward"],
    keys: ["note", "reward"],
    medical: [],
    special: ["guardian_name", "guardian_phone", "special_notes", "home_area"],
    general: ["note", "reward"],
};

const EMPTY_TAG = {
    type: "vehicle",
    label: "",
    display_name: "",
    message: "",
    data: {},
    public_fields: {
        display_name: true,
        message: true,
        type: true,
        vehicle_make_model: true,
        vehicle_plate: false,
        pet_name: true,
        pet_breed: true,
        note: true,
        reward: true,
        guardian_name: true,
        guardian_phone: true,
        special_notes: true,
        home_area: true,
    },
    contact: {
        mode: "masked",
        show_call: true,
        show_whatsapp: true,
        show_sms: true,
    },
    status: "active",
};

export default function TagEditPage() {
    const { id } = useParams();
    const isNew = !id || id === "new";
    const { t } = useI18n();
    const { user } = useAuth();
    const navigate = useNavigate();

    const [tag, setTag] = useState(isNew ? EMPTY_TAG : null);
    const [profile, setProfile] = useState(null);
    const [error, setError] = useState("");
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        if (isNew) return;
        (async () => {
            try {
                const { data } = await api.get(`/tags/${id}`);
                setTag(data);
                if (data.type === "medical") {
                    const { data: prof } = await api.get(`/tags/${id}/profile`);
                    setProfile(prof);
                }
            } catch (e) {
                setError(formatApiError(e));
            }
        })();
    }, [id, isNew]);

    const set = (path, value) => {
        setTag((prev) => {
            const next = { ...prev };
            if (path.startsWith("data.")) {
                next.data = { ...(prev.data || {}), [path.slice(5)]: value };
            } else if (path.startsWith("public_fields.")) {
                next.public_fields = { ...(prev.public_fields || {}), [path.slice(14)]: value };
            } else {
                next[path] = value;
            }
            return next;
        });
    };

    const onSave = async () => {
        setSaving(true);
        setError("");
        try {
            const payload = {
                label: tag.label,
                display_name: tag.display_name,
                message: tag.message,
                data: tag.data,
                public_fields: tag.public_fields,
                contact: tag.contact,
            };
            const savedTag = isNew
                ? (await api.post("/tags", { type: tag.type, ...payload })).data
                : (await api.patch(`/tags/${id}`, { ...payload, status: tag.status })).data;
            toast.success("Saved");
            const next = savedTag.type === "medical"
                ? `/tags/${savedTag.id}/medical`
                : `/tags/${savedTag.id}/qr`;
            navigate(next, { replace: true });
        } catch (e) {
            setError(formatApiError(e));
        } finally {
            setSaving(false);
        }
    };

    const onDelete = async () => {
        try {
            await api.delete(`/tags/${id}`);
            toast.success("Deleted");
            navigate("/dashboard", { replace: true });
        } catch (e) {
            toast.error(formatApiError(e));
        }
    };

    const typeFields = useMemo(() => TYPE_FIELDS[tag?.type || "general"] || [], [tag?.type]);

    if (!tag) {
        return <div className="text-muted-foreground animate-pulse-soft">{t("common.loading")}</div>;
    }

    let saveLabel = isNew ? t("tag_edit.create") : t("tag_edit.save");
    if (saving) saveLabel = t("common.loading");

    return (
        <div className="max-w-3xl mx-auto space-y-8" data-testid="tag-edit-root">
            <div className="flex items-center justify-between gap-3">
                <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="gap-1" data-testid="tag-edit-back">
                    <ArrowLeft className="h-4 w-4" /> {t("common.back")}
                </Button>
                <h1 className="font-display text-2xl sm:text-3xl font-bold tracking-tight">
                    {isNew ? t("tag_edit.new_title") : t("tag_edit.title")}
                </h1>
            </div>

            <TagBasicSection tag={tag} set={set} isNew={isNew} t={t} />
            <TagContactSection tag={tag} set={set} t={t} hasPhone={!!user?.phone} />
            <TagDataSection tag={tag} set={set} fields={typeFields} t={t} />
            <TagPublicFieldsSection tag={tag} set={set} t={t} />

            {tag.type === "medical" && !isNew && (
                <MedicalQuickLink id={id} profile={profile} navigate={navigate} />
            )}

            {error && <p className="text-sm text-destructive">{error}</p>}

            <div className="flex items-center justify-between gap-3 pt-4 border-t">
                {!isNew && <DeleteTagButton t={t} onDelete={onDelete} />}
                <Button onClick={onSave} disabled={saving} className="ml-auto rounded-full gap-2" data-testid="tag-save-btn">
                    <Save className="h-4 w-4" />
                    {saveLabel}
                </Button>
            </div>
        </div>
    );
}

function MedicalQuickLink({ id, profile, navigate }) {
    return (
        <div className="surface p-5 border-emergency/40">
            <div className="flex items-start gap-3">
                <HeartPulse className="h-5 w-5 text-destructive shrink-0" strokeWidth={2.5} />
                <div className="flex-1">
                    <div className="font-display font-bold">Medical Emergency Profile</div>
                    <p className="text-sm text-muted-foreground mt-1">
                        {profile?.emergency_mode ? "Emergency Mode is ON." : "Emergency Mode is OFF."}
                    </p>
                </div>
                <Button variant="outline" onClick={() => navigate(`/tags/${id}/medical`)} data-testid="manage-medical-btn">
                    Manage
                </Button>
            </div>
        </div>
    );
}

function DeleteTagButton({ t, onDelete }) {
    return (
        <AlertDialog>
            <AlertDialogTrigger asChild>
                <Button variant="ghost" className="text-destructive gap-1" data-testid="delete-tag-btn">
                    <Trash2 className="h-4 w-4" /> {t("tag_edit.delete_tag")}
                </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
                <AlertDialogHeader>
                    <AlertDialogTitle>{t("tag_edit.delete_tag")}</AlertDialogTitle>
                    <AlertDialogDescription>{t("tag_edit.delete_warning")}</AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                    <AlertDialogCancel data-testid="delete-cancel">{t("common.cancel")}</AlertDialogCancel>
                    <AlertDialogAction onClick={onDelete} data-testid="delete-confirm">{t("tag_edit.confirm_delete")}</AlertDialogAction>
                </AlertDialogFooter>
            </AlertDialogContent>
        </AlertDialog>
    );
}
