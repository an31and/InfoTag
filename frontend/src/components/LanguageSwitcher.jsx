import { Languages } from "lucide-react";
import { Button } from "../components/ui/button";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from "../components/ui/dropdown-menu";
import { useI18n } from "../lib/i18n";

export function LanguageSwitcher({ compact = false }) {
    const { lang, setLang, langs } = useI18n();
    const current = langs.find((l) => l.code === lang) || langs[0];
    return (
        <DropdownMenu>
            <DropdownMenuTrigger asChild>
                <Button
                    variant="ghost"
                    size={compact ? "sm" : "default"}
                    data-testid="lang-switcher-btn"
                    className="gap-2"
                >
                    <Languages className="h-4 w-4" />
                    <span className={`font-medium ${compact ? "hidden sm:inline" : ""}`}>{current.label}</span>
                </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="min-w-[160px]">
                {langs.map((l) => (
                    <DropdownMenuItem
                        key={l.code}
                        onClick={() => setLang(l.code)}
                        data-testid={`lang-option-${l.code}`}
                    >
                        <span className={lang === l.code ? "font-semibold" : ""}>
                            {l.label}
                        </span>
                    </DropdownMenuItem>
                ))}
            </DropdownMenuContent>
        </DropdownMenu>
    );
}
