import { useState } from "react";
import { Languages, X } from "lucide-react";

import { DEFAULT_LANG, useI18n } from "../lib/i18n";

const PROMPTED_KEY = "infotag_lang_prompted";

function alreadyPrompted() {
    try {
        return !!localStorage.getItem(PROMPTED_KEY);
    } catch {
        return true; // no storage → the prompt would reappear on every load; skip it
    }
}

function markPrompted() {
    try {
        localStorage.setItem(PROMPTED_KEY, "1");
    } catch {
        /* best-effort */
    }
}

/**
 * One-time language picker shown on the very first visit.
 * The site starts in Hindi (the default); this sheet lets the visitor switch
 * to English or any supported regional language in one tap. Dismissing keeps
 * Hindi and never asks again — the nav language switcher stays available.
 */
export function LanguagePrompt() {
    const { lang, setLang, langs, t } = useI18n();
    const [open, setOpen] = useState(() => !alreadyPrompted());

    if (!open) return null;

    const choose = (code) => {
        setLang(code);
        markPrompted();
        setOpen(false);
    };
    const dismiss = () => {
        markPrompted();
        setOpen(false);
    };

    return (
        <div
            className="fixed inset-0 z-[100] flex items-end sm:items-center justify-center bg-slate-950/60 backdrop-blur-sm p-0 sm:p-5"
            role="dialog"
            aria-modal="true"
            aria-label={t("common.language")}
            onClick={(e) => e.target === e.currentTarget && dismiss()}
            data-testid="language-prompt"
        >
            <div className="w-full sm:max-w-sm bg-background text-foreground rounded-t-3xl sm:rounded-3xl shadow-2xl p-6 animate-rise">
                <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-2.5">
                        <span className="w-9 h-9 rounded-xl bg-accent/15 text-accent grid place-items-center shrink-0">
                            <Languages className="h-5 w-5" />
                        </span>
                        <div>
                            <h2 className="font-display font-bold text-lg leading-tight">
                                अपनी भाषा चुनें
                            </h2>
                            <p className="text-xs text-muted-foreground">Choose your language</p>
                        </div>
                    </div>
                    <button
                        onClick={dismiss}
                        aria-label="Close"
                        className="p-1.5 rounded-full hover:bg-muted"
                        data-testid="language-prompt-close"
                    >
                        <X className="h-4 w-4" />
                    </button>
                </div>
                <div className="mt-5 grid grid-cols-2 gap-2">
                    {langs.map((l) => (
                        <button
                            key={l.code}
                            onClick={() => choose(l.code)}
                            className={`rounded-xl border px-4 py-3 text-sm font-semibold text-left transition-colors hover:border-accent ${
                                l.code === lang ? "border-accent bg-accent/10 text-accent" : "border-border"
                            }`}
                            data-testid={`language-prompt-${l.code}`}
                        >
                            {l.label}
                            {l.code === DEFAULT_LANG && (
                                <span className="block text-[10px] font-normal text-muted-foreground">
                                    डिफ़ॉल्ट · default
                                </span>
                            )}
                        </button>
                    ))}
                </div>
                <p className="mt-4 text-[11px] text-muted-foreground text-center">
                    आप इसे कभी भी ऊपर दिए भाषा बटन से बदल सकते हैं · You can change this anytime from the 🌐 button
                </p>
            </div>
        </div>
    );
}
