# Reading the dead-code baseline, 19 Sep 2026

`dead-code-before.txt` is the raw output of `scripts\dead_code.py frontend`, unedited.
This file is the triage, written the same day, because the raw output contains one
false positive large enough to destroy the product if D1 acts on it literally.

## unused_public_assets: 14 of the 17 are WRONG

The scanner reports every `public/muestras/*.jpg` and `*.webp` as unreferenced. They are
referenced, by template literal, which a literal-string scan cannot see:

    frontend/src/components/more-muestras.tsx:89   src={`/muestras/${item.key}-antes.jpg`}
    frontend/src/components/more-muestras.tsx:96   src={`/muestras/${item.key}-despues.jpg`}
    frontend/src/components/muestras.tsx:60        <source srcSet={`/muestras/${src}.webp`} .../>
    frontend/src/components/muestras.tsx:62        src={`/muestras/${src}.jpg`}

The keys come from `MUESTRAS` in `frontend/src/components/muestras.tsx`, which
`hero-proof.tsx:16` and `more-muestras.tsx:26` both import. These are the before/after
images: the first thing the landing page shows and the entire proof that the product
works. Deleting them because a scanner said "unused" is the failure this note exists to
prevent.

The other 3 need the same care, and I got them wrong on the first pass. There are five
svg files, not three, and four of them ARE used — from outside `frontend`, which is the
only tree this scanner walks:

    scripts/demo_server.py:33  PLACEHOLDERS = ["/next.svg", "/vercel.svg", "/globe.svg", "/window.svg"]

`demo_server.py` is the M6 local harness: it stands in for the signed gallery URLs so the
gallery renders four real images instead of four broken ones. Delete those svgs and the
local screenshot harness this very unit depends on starts producing broken images.

That leaves `public/file.svg` as the only public asset with no reference anywhere in the
repository. One file.

## orphan_modules: src/lib/utils.ts is real

No `@/lib/utils` import and no `cn(` call anywhere in `frontend/src`. It is the shadcn
`cn()` helper left behind when the components stopped using it. CLAUDE.md's clutter rules
name this file shape specifically ("no utils.py"), so it goes in D1.

## The shape of the mistake, twice

Both errors are the same error: the scanner is told to walk `frontend`, so a reference
that lives anywhere else - a template literal it cannot parse, or a Python file outside
the tree - reads as absence. `unused_public_assets` is not a list of dead files. It is a
list of files whose references this scanner could not see, and every entry needs a grep
across the whole repository before anyone touches it.

## What D1 has to do about it

Not an allowlist entry per muestra — that hides the gap rather than closing it, and the
next asset referenced by template literal reintroduces it silently. The asset rule needs
to understand a template literal with an interpolation: treat `` `/muestras/${x}-antes.jpg` ``
as matching the glob `public/muestras/*-antes.jpg`. Until that lands, no public asset is
deleted on this scanner's word alone.
