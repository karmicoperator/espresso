# MedScroll reader

Next.js app. Run it through `MedScroll.app` or `./start.command` from the repo root; both
pick the ports and tell this app which API to call.

- `components/ChartFigure.tsx` draws every chart kind from the typed spec, and owns the
  hover that shows the paper's own sentence.
- `components/FigureFigure.tsx` shows the paper's own images.
- `components/ExplainerReader.tsx` is the page: prose left, charts right, figures full width.
- `lib/types.ts` mirrors `backend/models/charts.py`. Change them together.

The API origin comes from `NEXT_PUBLIC_API_URL`, compiled in at build time.
