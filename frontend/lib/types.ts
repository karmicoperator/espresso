/** The API contract. Mirrors backend/models/charts.py. */

export type LocatorKind = "paragraph" | "table_cell" | "abstract" | "figure_caption";

export type Provenance = {
  locator: string;
  kind: LocatorKind;
  /** Verbatim span from the paper. This is what the checker matched the number against. */
  quote: string;
  section: string;
};

export type Datum = {
  label: string;
  value: number;
  low: number | null;
  high: number | null;
  n: number | null;
  events: number | null;
  group: string;
  note: string;
  higher_is_better: boolean | null;
  provenance: Provenance;
};

export type Annotation = { target: string; text: string };

export type ChartKind = "stat" | "bars" | "dots" | "forest" | "line" | "flow" | "diagram";

export type FigurePlate = {
  id: string;
  label: string;
  caption: string;
  file: string;
  width: number | null;
  height: number | null;
  kind: string;
  why: string;
  section_id: string;
};

export type DiagramNode = {
  id: string;
  label: string;
  note: string;
};

export type DiagramEdge = {
  source: string;
  target: string;
  label: string;
  provenance: Provenance;
  hedged: boolean;
};

export type Chart = {
  id: string;
  kind: ChartKind;
  title: string;
  subtitle: string;
  data: Datum[];
  nodes: DiagramNode[];
  edges: DiagramEdge[];
  annotation: Annotation | null;
  unit: string;
  value_label: string;
  category_label: string;
  log_scale: boolean;
  null_value: number | null;
  lower_is_better: boolean;
  favours_left: string;
  favours_right: string;
  caveat: string;
  source: string;
  section_id: string;
};

export type ReaderSection = {
  id: string;
  title: string;
  markdown: string;
  chart_ids: string[];
  figure_ids: string[];
};

export type VerificationReport = {
  checked: number;
  passed: number;
  rejections: { what: string; locator: string; reason: string }[];
};

export type Explainer = {
  paper_id: string;
  title: string;
  authors: string[];
  journal: string | null;
  published: string | null;
  doi: string | null;
  source_url: string | null;
  question: string;
  sections: ReaderSection[];
  charts: Chart[];
  figures: FigurePlate[];
  verification: VerificationReport;
  notes: string[];
};

export type ExplainerSummary = {
  paper_id: string;
  title: string;
  journal: string | null;
  published: string | null;
  chart_count: number;
};

/** A build in progress or recently finished. Mirrors backend/builds.py Job.public(). */
export type Job = {
  id: string;
  label: string;
  kind: "pubmed" | "pdf";
  status: "queued" | "running" | "done" | "failed";
  step: string;
  fraction: number;
  detail: string;
  elapsed: number;
  paper_id: string | null;
  title: string | null;
  error: { message: string; kind: string; url: string } | null;
};
