# espresso reader

Next.js app. Run it through `espresso.app` or `./start.command` from the repo root; both
pick the ports and tell this app which API to call.

- `components/ChartFigure.tsx` draws every chart kind from the typed spec, and owns the
  hover that shows the paper's own sentence.
- `components/FigureFigure.tsx` shows the paper's own images.
- `components/ExplainerReader.tsx` is the page: prose left, charts right, figures full width.
- `lib/types.ts` mirrors `backend/models/charts.py`. Change them together.

`app/api/[...path]/route.ts` forwards `/api/*` to the API at request time, so the page is
single-origin and the API port (`API_URL`, set by the launcher) is not part of the build.
The launchers serve a production build and rebuild it when a source file is newer;
`ESPRESSO_DEV=1 ./start.command` runs the dev server instead.
