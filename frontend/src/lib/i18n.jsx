// Tiny in-app i18n.  Falls back to English when a key is missing.
// Every language is a full dictionary in ./locales/<code>.js.
// English + Hindi ship in the main bundle (Hindi is the default language);
// the other Indian languages are code-split and fetched on first use so the
// first paint stays light on slow mobile connections.
import { createContext, useContext, useEffect, useMemo, useState } from "react";

import en from "./locales/en";
import hi from "./locales/hi";

const LANGS = [
    { code: "hi", label: "हिन्दी" },
    { code: "en", label: "English" },
    { code: "mr", label: "मराठी" },
    { code: "bn", label: "বাংলা" },
    { code: "ta", label: "தமிழ்" },
    { code: "te", label: "తెలుగు" },
    { code: "kn", label: "ಕನ್ನಡ" },
];

const LANG_CODES = LANGS.map((l) => l.code);

// Webpack turns this into one lazy chunk per locale file.
const loaders = {
    mr: () => import("./locales/mr"),
    bn: () => import("./locales/bn"),
    ta: () => import("./locales/ta"),
    te: () => import("./locales/te"),
    kn: () => import("./locales/kn"),
};

export const DEFAULT_LANG = "hi";

export function normalizeLang(code) {
    return LANG_CODES.includes(code) ? code : DEFAULT_LANG;
}

function get(obj, dotted) {
    return dotted.split(".").reduce((acc, k) => (acc == null ? acc : acc[k]), obj);
}

const I18nContext = createContext(null);

export function I18nProvider({ children }) {
    const stored = typeof window !== "undefined" ? localStorage.getItem("infotag_lang") : null;
    const [lang, setLang] = useState(normalizeLang(stored || DEFAULT_LANG));
    const [dicts, setDicts] = useState({ en, hi });

    useEffect(() => {
        try {
            localStorage.setItem("infotag_lang", lang);
            document.documentElement.lang = lang;
        } catch (err) {
            // localStorage may be unavailable (Safari private mode, SSR). Locale still
            // works in-memory — just won't survive a reload.
            console.warn("Locale persist skipped:", err?.message || err);
        }
    }, [lang]);

    useEffect(() => {
        if (dicts[lang] || !loaders[lang]) return;
        let cancelled = false;
        loaders[lang]()
            .then((mod) => {
                if (!cancelled) setDicts((d) => ({ ...d, [lang]: mod.default }));
            })
            .catch((err) => console.warn(`Couldn't load locale ${lang}:`, err?.message || err));
        return () => {
            cancelled = true;
        };
    }, [lang, dicts]);

    const value = useMemo(() => {
        const t = (key) => {
            const v = get(dicts[lang] || {}, key);
            if (v != null) return v;
            return get(en, key) ?? key;
        };
        return { lang, setLang: (l) => setLang(normalizeLang(l)), t, langs: LANGS };
    }, [lang, dicts]);

    return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
    const ctx = useContext(I18nContext);
    if (!ctx) throw new Error("useI18n must be used inside I18nProvider");
    return ctx;
}
