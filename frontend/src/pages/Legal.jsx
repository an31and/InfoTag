import { Link } from "react-router-dom";
import { ArrowLeft, Tag } from "lucide-react";

function LegalLayout({ title, children }) {
    return (
        <div className="min-h-screen">
            <header className="border-b">
                <div className="mx-auto max-w-3xl px-4 sm:px-8 h-14 flex items-center justify-between">
                    <Link to="/" className="font-display font-black inline-flex items-center gap-2" data-testid="legal-brand">
                        <Tag className="h-4 w-4 text-accent" /> Info-<span className="text-accent">Tag</span>
                    </Link>
                    <Link to="/" className="text-sm text-muted-foreground hover:text-foreground inline-flex items-center gap-1">
                        <ArrowLeft className="h-4 w-4" /> Home
                    </Link>
                </div>
            </header>
            <article className="mx-auto max-w-3xl px-4 sm:px-8 py-10 prose prose-neutral dark:prose-invert">
                <h1 className="font-display text-3xl font-black tracking-tight">{title}</h1>
                {children}
            </article>
        </div>
    );
}

export function PrivacyPage() {
    return (
        <LegalLayout title="Privacy policy">
            <p>
                Info-Tag is a privacy-first, free public-service smart-tag ecosystem from India. We collect the
                minimum data needed to help reunite items with owners and to surface medical emergency
                information when explicitly consented to.
            </p>
            <h2>What we store</h2>
            <ul>
                <li>Your email and a bcrypt-hashed password (or your Google profile if you sign in with Google).</li>
                <li>Tags you create, the message you choose to display, and the public fields you toggle on.</li>
                <li>Anonymous scan counts of your tags (we hash IPs — we never store the raw IP).</li>
                <li>Messages a finder chooses to send to you, plus optional approximate location they share.</li>
            </ul>
            <h2>What we do NOT store</h2>
            <ul>
                <li>Your phone number is never shown to finders.</li>
                <li>Raw IP addresses — only short hashes used for rate-limiting.</li>
            </ul>
            <h2>Your rights</h2>
            <p>
                You can export every byte of your data from the Settings page, or delete your account at any time.
                Deletion is irreversible and removes all your tags, scans and finder messages.
            </p>
        </LegalLayout>
    );
}

export function TermsPage() {
    return (
        <LegalLayout title="Terms of service">
            <p>
                Info-Tag is provided free of cost as a public service. It is offered "as is" with no warranty of any
                kind. We do our best to keep the service available and secure, but we are not liable for losses
                arising from the use, misuse or unavailability of Info-Tag.
            </p>
            <ul>
                <li>You must own the items you tag.</li>
                <li>Medical Emergency Mode is a convenience — not a substitute for professional ID or care.</li>
                <li>Abusive, illegal, or spammy use is prohibited; we may revoke access without notice.</li>
            </ul>
            <p>Questions? Email an.31and@gmail.com.</p>
        </LegalLayout>
    );
}

export function MedicalDisclaimerPage() {
    return (
        <LegalLayout title="Medical disclaimer">
            <p className="text-destructive font-semibold">
                Wrong medical information is dangerous. Please double-check every field before saving.
            </p>
            <p>
                The Medical Emergency Mode on Info-Tag shows the information you, the owner, have entered and given
                consent to display. It is intended as a convenience for first responders and bystanders — it is
                not a verified medical record. Always verify identity and seek qualified care.
            </p>
            <p>
                Info-Tag does not provide medical advice, diagnosis or treatment. We are not responsible for actions
                taken based on the information displayed.
            </p>
        </LegalLayout>
    );
}
