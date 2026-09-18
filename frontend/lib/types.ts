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
  /** chain, fork or join; set by the backend. */
  shape?: string;
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
  /** Numbers in the prose looked up in the paper; misses are marked on the page. */
  prose_checked?: number;
  prose_unmatched?: { section_id: string; number: string; context: string }[];
};

/** What the paper asked and found, checked like a plotted value against its quote. */
export type BottomLine = {
  question: string;
  answer: string;
  provenance: Provenance;
  /** The figure in the answer that states the finding, verified by the gate; empty when none. */
  effect?: string;
  /** better, worse, no_difference or mixed: the colour of that figure. */
  verdict?: string;
};

/** One arm's absolute rate for the primary outcome, verified against its quote. */
export type RiskArm = {
  label: string;
  value: number;
  events: number | null;
  n: number | null;
  provenance: Provenance;
};

export type AbsoluteRisk = {
  outcome: string;
  timeframe: string;
  comparator: RiskArm;
  intervention: RiskArm;
  higher_is_better: boolean;
};

/** Computed once on the API from the two verified rates. Always marked derived. */
export type AbsoluteRiskDerived = {
  derived: true;
  per_1000: { comparator: number; intervention: number };
  difference_per_1000: number;
  direction: "fewer" | "more";
  favours_intervention: boolean | null;
  relative_change_pct: number | null;
  number_needed?: number;
  number_needed_kind?: "to treat" | "to harm";
};

/** A defined term. With a provenance the definition shown is the paper's own sentence. */
export type Term = {
  term: string;
  definition: string;
  provenance: Provenance | null;
};

/** A prose sentence that states the same printed fact as a chart element. */
export type Link = {
  section_id: string;
  sentence: string;
  chart_id: string;
  kind: "datum" | "edge";
  index: number;
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
  bottom_line?: BottomLine | null;
  absolute_risk?: AbsoluteRisk | null;
  absolute_risk_derived?: AbsoluteRiskDerived | null;
  terms?: Term[];
  links?: Link[];
  /** The paper's own paragraph behind each cited locator. */
  sources?: Record<string, string>;
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
  reading_minutes?: number;
  source?: "pmc" | "pdf";
  /** Built with the bottom line and prose check; older builds were not. */
  checked?: boolean;
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

/** Mirrors backend/settings.py current(). Keys are never included, only whether one is set. */
export type ProviderView = {
  label: string;
  help: string;
  model: string;
  default_model: string;
  needs_key: boolean;
  key_set: boolean;
  key_hint: string;
  base_url: string | null;
  endpoint: string | null;
};

export type SettingsView = {
  provider: string;
  problem: string;
  providers: Record<string, ProviderView>;
  env_path: string;
};

export type Health = {
  app: string;
  status: string;
  services: Record<string, string>;
};
