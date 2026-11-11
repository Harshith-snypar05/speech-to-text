import type { ReactNode } from "react";

export interface LegalSection { id: string; title: string; body: ReactNode }

/** Long-form legal reading layout: title block, sticky contents list on wide screens, one violet panel of numbered sections. */
export function LegalPage({ eyebrow, title, updated, intro, sections }: { eyebrow: string; title: string; updated: string; intro: ReactNode; sections: LegalSection[] }) {
  return (
    <main className="mx-auto max-w-[1100px] px-4 pb-24 pt-10 sm:px-8 sm:pt-16">
      <header className="max-w-3xl">
        <p className="text-sm font-semibold uppercase tracking-[0.16em] text-violet">{eyebrow}</p>
        <h1 className="mt-3 text-4xl font-bold tracking-tight sm:text-5xl">{title}</h1>
        <p className="mt-3 text-sm text-ink-3">Last updated {updated}</p>
        <div className="mt-6 text-lg leading-relaxed text-ink-2">{intro}</div>
      </header>

      <div className="mt-12 grid gap-10 lg:grid-cols-[240px_1fr]">
        <nav aria-label="Contents" className="hidden lg:block">
          <div className="sticky top-28">
            <div className="mb-3 text-xs font-semibold uppercase tracking-wider text-ink-3">Contents</div>
            <ol className="space-y-1 border-l border-line">
              {sections.map((s, i) => (
                <li key={s.id}>
                  <a href={`#${s.id}`} className="-ml-px block border-l border-transparent py-1.5 pl-4 text-sm text-ink-2 transition-colors hover:border-violet hover:text-ink">
                    <span className="tabular mr-1.5 text-ink-3">{i + 1}.</span>{s.title}
                  </a>
                </li>
              ))}
            </ol>
          </div>
        </nav>

        <article className="sl-panel rounded-[var(--radius-card)] p-6 sm:p-10">
          <div className="space-y-10">
            {sections.map((s, i) => (
              <section key={s.id} id={s.id} className="scroll-mt-28">
                <h2 className="text-xl font-semibold tracking-tight sm:text-2xl"><span className="tabular mr-2 text-violet">{i + 1}.</span>{s.title}</h2>
                <div className="mt-3 space-y-3 leading-relaxed text-ink-2 [&_a]:font-medium [&_a]:text-primary [&_a]:underline [&_li]:pl-1 [&_strong]:text-ink [&_ul]:list-disc [&_ul]:space-y-1.5 [&_ul]:pl-5">{s.body}</div>
              </section>
            ))}
          </div>
        </article>
      </div>
    </main>
  );
}

export const CONTACT_EMAIL = "info@scriptliv.com";
