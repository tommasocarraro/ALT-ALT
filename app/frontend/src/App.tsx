import React, { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, Link, useNavigate, useParams, useLocation } from "react-router-dom";
import {createPortal} from "react-dom";
import { Document, Page, pdfjs } from "react-pdf";

pdfjs.GlobalWorkerOptions.workerSrc = `${process.env.PUBLIC_URL}/pdf.worker.min.mjs`;

// -------------------------------
// Types
// -------------------------------

type CreateProjectResponse = {
  status: "ok";
  project_id: number;
  diagram_pdf_path: string; // server filesystem path
  bearings_saved: string[]; // list of bearing codes
};

type ArrangementType = "SP" | "BSB" | "OA"; // Simple Pivot, Bearing-Spacer-Bearing, Over-Axle

type Material = "carbon" | "alloy";

type SpacerMobility = "moves" | "stuck";

type OAType = "short" | "long";

type ComponentType = "frame" | "hub" | "freehub";

type FreehubBody = "hg_microspline" | "xd_xdr";

interface ArrangementBSBDetails {
  hasSpacer: boolean | null;
  spacerLenGe10mm: boolean | null;
  spacerMobility: SpacerMobility | null; // only if spacerLenGe10mm === true
}

interface ArrangementOADetails {
  axleLength: OAType | null;
}

interface ArrangementFreehubDetails {
  body: FreehubBody | null;
  oneSide: boolean | null; // both bearings installed from the same side
}

interface ArrangementForm {
  name: string;
  material: Material | null;
  type: ArrangementType | null;
  // bearing codes per position along the axis; two codes in one slot = double-stacked
  slots: string[][];
  bsb: ArrangementBSBDetails;
  oa: ArrangementOADetails;
  component: ComponentType | null;
  hasCenterLock: boolean | null; // only if component === "hub"
  freehub: ArrangementFreehubDetails; // only if component === "freehub"
}

interface SavedArrangement extends ArrangementForm {
  id: string; // server id (string for simplicity)
}

// a bearing of the project, with where its code and its dimensions come from
interface BearingInfo {
  code: string;
  quantity: number | null;
  foundIn: "diagram" | "web";
  reference: string | null; // callout label in the diagram, or the part number it was looked up from
  sourceUrl: string | null;
  innerDiameter: number | null;
  outerDiameter: number | null;
  width: number | null;
  dimensionsSource: "standard" | "code" | "web" | null;
  dimensionsSourceUrl: string | null;
}

// a bearing the diagram shows without a code, and that could not be looked up
interface UnresolvedReference {
  description: string;
  part_number: string | null;
  note: string | null;
}

// what the rule engine returns for a project: jobs per arrangement, and the cart
interface StackItem {
  kind: "piece" | "workpiece";
  name: string;
  text: string | null;
  resolved: boolean;
}

interface ToolJob {
  title: string;
  bearing: string | null;
  stack: StackItem[];
  action: string;
  alternatives: string[];
  notes: string[];
  svg: string;
  diagram_url: string | null;
}

interface ToolsResult {
  arrangements: { arrangement: string; rule_set_name: string; assumptions: string[]; jobs: ToolJob[] }[];
  cart: { currency: string; total: number; lines: CartLine[] };
}

// one line of the cart: computed by the rules or added by hand, possibly changed or removed by the user
interface CartLine {
  key: string;
  piece: string;
  sku: string | null; // null while the size is still to be chosen
  name: string;
  qty: number;
  unit_price: number | null;
  origin: "rule" | "added";
  edited: boolean;
  removed: boolean;
  reason: string | null;
}

interface CatalogItem {
  sku: string;
  name: string;
  piece: string;
  unit_price: number;
}

interface Project {
  id: number;
  title: string;
  diagramUrl: string;
  pdfUrl: string; // browser-servable URL for the PDF
  bearingCodes: string[];
  bearings: BearingInfo[];
  unresolvedReferences: UnresolvedReference[];
  arrangements: SavedArrangement[];
}

// -------------------------------
// Utilities
// -------------------------------

function mapServerPathToPublicUrl(serverPath: string): string {
  const normalized = serverPath.replaceAll("\\", "/");
  const filename = normalized.split("/").pop() || normalized;
  return `/static/diagrams/${filename}`;
}

function clsx(...parts: Array<string | false | undefined>) {
  return parts.filter(Boolean).join(" ");
}

const MAX_STACK = 2; // a seat holds one bearing, or two when double-stacked

function slotCount(type: ArrangementType | null): number {
  return type === null ? 0 : type === "SP" ? 1 : 2;
}

// keeps the bearings already placed when the arrangement type changes
function resizeSlots(slots: string[][], type: ArrangementType): string[][] {
  return Array.from({ length: slotCount(type) }, (_, i) => slots[i] ?? []);
}

function slotLabels(type: ArrangementType | null, component: ComponentType | null): string[] {
  if (type === "SP") return ["Bearing seat"];
  if (component === "hub") return ["Disc side", "Drive side"];
  if (component === "freehub") return ["Inboard", "Outboard"];
  return ["Side A", "Side B"];
}

function formatSequence(a: ArrangementForm): string {
  const between = a.type === "OA" ? "axle" : a.bsb?.hasSpacer === false ? "" : "spacer";
  return a.slots.map((s) => (s.length ? s.join(" + ") : "?")).join(between ? ` – ${between} – ` : " – ");
}

// -------------------------------
// App Root + Routing
// -------------------------------

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-slate-50 text-slate-900">
        <header className="sticky top-0 z-10 bg-white/80 backdrop-blur border-b border-slate-200">
          <div className="mx-auto max-w-6xl px-4 py-3 flex items-center justify-between">
            <Link to="/" className="text-xl font-semibold">Bike Bearing Press Planner</Link>
            <HeaderActions />
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-6">
          <Routes>
            <Route path="/" element={<ProjectsPage />} />
            <Route path="/projects/:id" element={<WorkspacePage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

function NewProjectButton() {
  const [open, setOpen] = React.useState(false);
  return (
    <>
      <button aria-label="open-new-project" className="px-4 py-2 rounded-2xl bg-slate-900 text-white hover:bg-slate-800 shadow" onClick={() => setOpen(true)}>+ New Project</button>
      {open && <NewProjectModal onClose={() => setOpen(false)} onCreated={(p) => { setOpen(false); window.location.assign(`/projects/${p.id}`); }} />}
    </>
  );
}

function HeaderActions() {
  const { pathname } = useLocation();
  // Only show the button on the main list page
  const showNew = pathname === "/";
  return showNew ? <NewProjectButton /> : null;
}

// -------------------------------
// Pages
// -------------------------------

function ProjectsPage() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch("/projects");
        if (!res.ok) throw new Error(`Failed to load projects (${res.status})`);
        const data = await res.json();
        const mapped: Project[] = data.map((p: any) => ({
          id: p.id,
          title: p.title,
          diagramUrl: p.diagram_url,
          pdfUrl: mapServerPathToPublicUrl(p.diagram_pdf_path),
          bearingCodes: p.bearing_codes,
          bearings: [],
          unresolvedReferences: [],
          arrangements: [],
        }));
        setProjects(mapped);
      } catch (e: any) { setError(e.message); }
    })();
  }, []);

  if (error) return <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-red-700">{error}</div>;
  if (projects === null) return <div className="text-slate-600">Loading projects…</div>;

  return projects.length === 0 ? (
    <EmptyState onCreate={() => (document.querySelector("button[aria-label='open-new-project']") as HTMLButtonElement)?.click()} />
  ) : (
    <ProjectList projects={projects} onOpen={(p) => (window.location.href = `/projects/${p.id}`)} />
  );
}

function WorkspacePage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`/projects/${id}`);
        if (!res.ok) throw new Error(`Failed to load project (${res.status})`);
        const p = await res.json();
        const mapped: Project = {
          id: p.id,
          title: p.title,
          diagramUrl: p.diagram_url,
          pdfUrl: mapServerPathToPublicUrl(p.diagram_pdf_path),
          bearingCodes: p.bearing_codes,
          bearings: p.bearings || [],
          unresolvedReferences: p.unresolved_references || [],
          arrangements: p.arrangements || [],
        };
        setProject(mapped);
      } catch (e: any) { setError(e.message); }
    })();
  }, [id]);

  if (error) return <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-red-700">{error}</div>;
  if (!project) return <div className="text-slate-600">Loading workspace…</div>;

  return (
    <ProjectWorkspace project={project} onBack={() => navigate("/")} onUpdate={setProject} />
  );
}

// -------------------------------
// Reusable pieces
// -------------------------------

function EmptyState({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="rounded-3xl border border-dashed border-slate-300 p-10 text-center bg-white shadow-sm">
      <h2 className="text-lg font-semibold mb-2">No projects yet</h2>
      <p className="text-slate-600 mb-6">Create your first project to get started.</p>
      <button className="px-4 py-2 rounded-2xl bg-slate-900 text-white hover:bg-slate-800" onClick={onCreate}>
        + New Project
      </button>
    </div>
  );
}

function ProjectList({ projects, onOpen }: { projects: Project[]; onOpen: (p: Project) => void }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {projects.map((p) => (
        <div key={p.id} className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-start justify-between">
            <div>
              <h3 className="text-lg font-semibold">{p.title}</h3>
              <p className="text-sm text-slate-500 truncate max-w-sm">{p.diagramUrl}</p>
            </div>
            <button className="px-3 py-1.5 rounded-xl bg-slate-900 text-white hover:bg-slate-800" onClick={() => onOpen(p)}>Open</button>
          </div>
          <div className="mt-3 text-sm text-slate-600">Bearings detected: {p.bearingCodes.length}</div>
        </div>
      ))}
    </div>
  );
}

function Spinner({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className="size-4 rounded-full border-2 border-slate-300 border-t-slate-900 animate-spin" />
      {label && <span>{label}</span>}
    </span>
  );
}

// -------------------------------
// New Project Modal (calls /create_project and then navigates to workspace)
// -------------------------------

function NewProjectModal({ onClose, onCreated }: { onClose: () => void; onCreated: (p: Project) => void }) {
  const [title, setTitle] = useState("");
  const [url, setUrl] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch("/create_project", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, url }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err?.detail || `Request failed: ${res.status}`);
      }
      const data: CreateProjectResponse = await res.json();
      const project: Project = {
        id: data.project_id,
        title,
        diagramUrl: url,
        pdfUrl: mapServerPathToPublicUrl(data.diagram_pdf_path),
        bearingCodes: data.bearings_saved,
        bearings: [],
        unresolvedReferences: [],
        arrangements: [],
      };
      onCreated(project);
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setSubmitting(false);
    }
  }

  return createPortal(
    <div
      className="fixed inset-0 z-[9999] bg-black/40 backdrop-blur-sm overflow-y-auto"
      role="dialog"
      aria-modal="true"
    >
      <div className="fixed inset-0 bg-black/40 backdrop-blur-sm overflow-y-auto z-50">
        <div className="min-h-full flex items-start justify-center p-4">
          <div className="mt-10 mb-10 w-full max-w-lg rounded-3xl bg-white p-6 shadow-xl max-h-[90vh] overflow-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">Create new project</h2>
              <button onClick={onClose} className="text-slate-500 hover:text-slate-800">✕</button>
            </div>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1">Project title</label>
                <input
                  className="w-full rounded-xl border border-slate-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-slate-900"
                  placeholder="e.g., YT Capra"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  required
                  autoFocus
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Diagram URL</label>
                <input
                  className="w-full rounded-xl border border-slate-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-slate-900"
                  placeholder="https://…/tech-docs/your-bike-exploded-diagram.pdf"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  required
                  type="url"
                />
              </div>

              {error && (
                <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
              )}

              <div className="flex items-center justify-end gap-3 pt-2">
                <button type="button" onClick={onClose} className="px-4 py-2 rounded-2xl border border-slate-300 hover:bg-slate-50">Cancel</button>
                <button type="submit" disabled={submitting} className={clsx("px-4 py-2 rounded-2xl bg-slate-900 text-white shadow", submitting && "opacity-70 cursor-not-allowed")}>{submitting ? <Spinner label="Creating…" /> : "Create project"}</button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}

// -------------------------------
// Workspace (PDF on left, interaction on right)
// -------------------------------

function ProjectWorkspace({ project, onBack, onUpdate }: { project: Project; onBack: () => void; onUpdate: (p: Project) => void }) {
  const [numPages, setNumPages] = useState<number | null>(null);
  const [page, setPage] = useState(1);
  const [scale, setScale] = useState(1.2);

  const canPrev = page > 1;
  const canNext = numPages ? page < numPages : false;

  // drag the diagram with the mouse to move around it, like a map
  const viewer = React.useRef<HTMLDivElement>(null);
  const drag = React.useRef<{ x: number; y: number; left: number; top: number } | null>(null);
  const [dragging, setDragging] = useState(false);
  const startDrag = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.pointerType !== "mouse" || e.button !== 0 || !viewer.current) return; // touch already scrolls by itself
    drag.current = { x: e.clientX, y: e.clientY, left: viewer.current.scrollLeft, top: viewer.current.scrollTop };
    viewer.current.setPointerCapture(e.pointerId);
    setDragging(true);
  };
  const moveDrag = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!drag.current || !viewer.current) return;
    viewer.current.scrollLeft = drag.current.left - (e.clientX - drag.current.x);
    viewer.current.scrollTop = drag.current.top - (e.clientY - drag.current.y);
  };
  const endDrag = () => { drag.current = null; setDragging(false); };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
      {/* Left: PDF viewer */}
      <div className="lg:col-span-7 rounded-3xl border border-slate-200 bg-white p-3 shadow-sm">
        <div className="flex items-center justify-between px-2 pb-2 border-b border-slate-200">
          <div className="flex items-center gap-2">
            <button className="px-3 py-1.5 rounded-xl border border-slate-300 hover:bg-slate-50" onClick={onBack}>← Back</button>
            <div className="text-sm text-slate-600">{project.title}</div>
          </div>
          <div className="flex items-center gap-2">
            <button disabled={!canPrev} onClick={() => setPage(p => Math.max(1, p - 1))} className="px-2 py-1 rounded-lg border border-slate-300 disabled:opacity-50">Prev</button>
            <span className="text-sm">Page {page}{numPages ? ` / ${numPages}` : ""}</span>
            <button disabled={!canNext} onClick={() => setPage(p => (numPages ? Math.min(numPages, p + 1) : p))} className="px-2 py-1 rounded-lg border border-slate-300 disabled:opacity-50">Next</button>
            <div className="w-px h-5 bg-slate-300 mx-1" />
            <button onClick={() => setScale(s => Math.max(0.2, Number((s - 0.1).toFixed(2))))} className="px-2 py-1 rounded-lg border border-slate-300">−</button>
            <span className="w-10 text-center text-sm">{Math.round(scale * 100)}%</span>
            <button onClick={() => setScale(s => Math.min(5, Number((s + 0.1).toFixed(2))))} className="px-2 py-1 rounded-lg border border-slate-300">+</button>
          </div>
        </div>
        <div ref={viewer} className={clsx("relative overflow-auto max-h-[75vh] py-3 select-none", dragging ? "cursor-grabbing" : "cursor-grab")}
             onPointerDown={startDrag} onPointerMove={moveDrag} onPointerUp={endDrag} onPointerCancel={endDrag}>
          {/* wrapper can grow wider than the container, enabling horizontal scroll */}
          <div className="inline-block min-w-max">
            <Document file={project.pdfUrl}
                      onLoadSuccess={(doc) => setNumPages(doc.numPages)}
                      loading={<div className="p-10 text-slate-500">Loading PDF…</div>}>
              <Page
                pageNumber={page}
                scale={scale}
                renderTextLayer={false}
                renderAnnotationLayer={false}
              />
            </Document>
          </div>
        </div>
      </div>

      {/* Right: Interaction */}
      <ProjectInteractionPanel project={project} onUpdate={onUpdate} />

      {/* Below: what the saved arrangements need */}
      <ToolsSection project={project} />
    </div>
  );
}

// -------------------------------
// Tools, instructions and cart for the saved arrangements
// -------------------------------

function ToolsSection({ project }: { project: Project }) {
  const [tools, setTools] = useState<ToolsResult | null>(null);
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [version, setVersion] = useState(0); // bumped after every change to the cart
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  // recompute whenever an arrangement is added or edited
  const signature = JSON.stringify(project.arrangements);

  useEffect(() => {
    if (project.arrangements.length === 0) { setTools(null); return; }
    (async () => {
      try {
        const res = await fetch(`/projects/${project.id}/tools`);
        if (!res.ok) throw new Error(`Failed to load tools (${res.status})`);
        setTools(await res.json());
        setError(null);
      } catch (e: any) { setError(e.message); }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project.id, signature, version]);

  useEffect(() => {
    fetch("/catalog").then((r) => r.json()).then(setCatalog).catch(() => setCatalog([]));
  }, []);

  // changes one cart line (or adds a piece when key is null); reset undoes the change
  const editCart = async (key: string | null, sku: string | null, qty: number) => {
    await fetch(`/projects/${project.id}/cart`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key, sku, qty }) });
    setVersion((v) => v + 1);
  };
  const resetCartLine = async (key: string) => {
    await fetch(`/projects/${project.id}/cart?key=${encodeURIComponent(key)}`, { method: "DELETE" });
    setVersion((v) => v + 1);
  };

  const downloadInstructions = async () => {
    setDownloading(true);
    try {
      const res = await fetch(`/projects/${project.id}/instructions.pdf`);
      if (!res.ok) throw new Error(`Failed to make the PDF (${res.status})`);
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = `${project.title} - instructions.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) { setError(e.message); }
    setDownloading(false);
  };

  if (project.arrangements.length === 0) return null;
  return (
    <div className="lg:col-span-12 rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="pb-3 border-b border-slate-200">
        <h3 className="text-lg font-semibold">Tools and instructions</h3>
      </div>
      {error && <div className="mt-3 rounded-xl border border-red-200 bg-red-50 p-3 text-red-700">{error}</div>}
      {!tools ? <div className="mt-3 text-sm text-slate-500">Working out the tools…</div> : (
        <>
          <CartView cart={tools.cart} catalog={catalog} onEdit={editCart} onReset={resetCartLine} />
          <div className="mt-6 pt-4 border-t border-slate-200 flex items-center justify-between">
            <div className="text-sm font-medium">Instructions</div>
            <button className="px-3 py-1.5 rounded-xl border border-slate-300 hover:bg-slate-50 disabled:opacity-50" disabled={downloading}
                    onClick={downloadInstructions}>{downloading ? "Making the PDF…" : "Download instructions (PDF)"}</button>
          </div>
          {tools.arrangements.map((a, i) => (
            <div key={i} className="mt-6">
              <div className="font-semibold">{a.arrangement} <span className="font-normal text-slate-500">• {a.rule_set_name}</span></div>
              {a.assumptions.map((x, k) => <div key={k} className="text-sm text-amber-700">Assumed: {x}</div>)}
              <div className="mt-2 grid grid-cols-1 xl:grid-cols-2 gap-3">
                {a.jobs.map((job, k) => <JobCard key={k} n={k + 1} job={job} />)}
              </div>
            </div>
          ))}
        </>
      )}
    </div>
  );
}

function CartView({ cart, catalog, onEdit, onReset }: {
  cart: ToolsResult["cart"];
  catalog: CatalogItem[];
  onEdit: (key: string | null, sku: string | null, qty: number) => void;
  onReset: (key: string) => void;
}) {
  const [addSku, setAddSku] = useState("");
  const [addQty, setAddQty] = useState(1);
  const money = (x: number) => `${x.toFixed(2)} ${cart.currency}`;
  const field = "rounded-lg border border-slate-300 px-2 py-1 text-sm";

  return (
    <div className="mt-4">
      <div className="text-sm font-medium mb-2">Cart</div>
      <div className="text-xs text-slate-500 mb-2">Pieces are reused from one job to the next, so each quantity is the most that a single job needs. Change a size or a quantity, remove a line, or add a piece: your changes are kept.</div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-slate-500 border-b border-slate-200">
            <th className="py-1 pr-2 font-normal w-20">Qty</th><th className="py-1 pr-2 font-normal">Piece</th>
            <th className="py-1 pr-2 font-normal">Part no.</th><th className="py-1 pr-2 font-normal text-right">Each</th>
            <th className="py-1 pr-2 font-normal text-right">Total</th><th className="py-1 font-normal w-24"></th>
          </tr>
        </thead>
        <tbody>
          {cart.lines.map((line) => {
            // other sizes and materials of the same kind of piece
            const options = catalog.filter((c) => c.piece === line.piece);
            return (
              <tr key={line.key} className={clsx("border-b border-slate-100", line.removed && "opacity-50", !line.sku && "bg-amber-50")}>
                <td className="py-1 pr-2">
                  <input type="number" min={0} className={clsx(field, "w-16")} value={line.qty} disabled={line.removed}
                         onChange={(e) => onEdit(line.key, line.sku, Math.max(0, Number(e.target.value)))} />
                </td>
                <td className="py-1 pr-2">
                  <select className={clsx(field, line.removed && "line-through")} value={line.sku ?? ""} disabled={line.removed}
                          onChange={(e) => onEdit(line.key, e.target.value, line.qty)}>
                    {!line.sku && <option value="">{line.name}: choose…</option>}
                    {options.map((c) => <option key={c.sku} value={c.sku}>{c.name}</option>)}
                  </select>
                  {!line.sku && line.reason && <span className="ml-2 text-xs text-amber-700">{line.reason}</span>}
                  {line.origin === "added" && <span className="ml-2 text-xs text-slate-500">added by hand</span>}
                  {line.origin === "rule" && line.edited && !line.removed && <span className="ml-2 text-xs text-slate-500">changed</span>}
                </td>
                <td className="py-1 pr-2 text-slate-500">{line.sku ?? ""}</td>
                <td className="py-1 pr-2 text-right">{line.unit_price !== null ? money(line.unit_price) : ""}</td>
                <td className="py-1 pr-2 text-right">{line.unit_price !== null && !line.removed ? money(line.qty * line.unit_price) : ""}</td>
                <td className="py-1 text-right whitespace-nowrap">
                  {line.origin === "added" ? (
                    <button className="text-slate-600 underline" onClick={() => onReset(line.key)}>Remove</button>
                  ) : line.removed ? (
                    <button className="text-slate-600 underline" onClick={() => onReset(line.key)}>Restore</button>
                  ) : (
                    <>
                      {line.edited && <button className="text-slate-600 underline mr-2" onClick={() => onReset(line.key)}>Reset</button>}
                      <button className="text-slate-600 underline" onClick={() => onEdit(line.key, line.sku, 0)}>Remove</button>
                    </>
                  )}
                </td>
              </tr>
            );
          })}
          <tr>
            <td className="py-2 pr-2">
              <input type="number" min={1} className={clsx(field, "w-16")} value={addQty} onChange={(e) => setAddQty(Math.max(1, Number(e.target.value)))} />
            </td>
            <td className="py-2 pr-2" colSpan={4}>
              <select className={field} value={addSku} onChange={(e) => setAddSku(e.target.value)}>
                <option value="">Add a piece…</option>
                {catalog.map((c) => <option key={c.sku} value={c.sku}>{c.name} ({c.unit_price.toFixed(2)})</option>)}
              </select>
            </td>
            <td className="py-2 text-right">
              <button className="px-3 py-1 rounded-xl border border-slate-300 hover:bg-slate-50 disabled:opacity-50" disabled={!addSku}
                      onClick={() => { onEdit(null, addSku, addQty); setAddSku(""); setAddQty(1); }}>Add</button>
            </td>
          </tr>
        </tbody>
        <tfoot>
          <tr><td colSpan={4} className="py-2 pr-2 text-right font-medium">Total, without the pieces still to choose</td><td className="py-2 pr-2 text-right font-medium">{money(cart.total)}</td><td></td></tr>
        </tfoot>
      </table>
    </div>
  );
}

function JobCard({ n, job }: { n: number; job: ToolJob }) {
  return (
    <div className="rounded-2xl border border-slate-200 p-3 text-sm">
      <div className="font-medium">{n}. {job.title}{job.bearing ? `: ${job.bearing}` : ""}</div>
      <div className="mt-2 overflow-x-auto">
        <img alt={`Section drawing: ${job.title}`} src={`data:image/svg+xml;utf8,${encodeURIComponent(job.svg)}`} className="max-w-full h-auto" />
      </div>
      <ol className="mt-2 space-y-0.5">
        {job.stack.map((item, i) => (
          <li key={i} className={clsx("flex gap-2", !item.resolved && "text-amber-700")}>
            <span className="font-semibold w-4 shrink-0">{String.fromCharCode(97 + i)}</span>
            <span>{item.kind === "workpiece" ? <em>{item.name}</em> : <><span className="font-medium">{item.name}</span>{item.text ? `: ${item.text}` : ""}</>}</span>
          </li>
        ))}
      </ol>
      <div className="mt-2">{job.action}</div>
      {job.alternatives.map((x, i) => <div key={i} className="mt-1 text-slate-600">Alternative for the {x}</div>)}
      {job.notes.map((x, i) => <div key={i} className="mt-1 text-xs text-slate-500">{x}</div>)}
      {job.diagram_url ? (
        <details className="mt-2">
          <summary className="cursor-pointer text-slate-600">Official ALT/ALT diagram</summary>
          <img alt={`Official diagram: ${job.title}`} src={job.diagram_url} className="mt-2 w-full rounded-xl border border-slate-200" />
        </details>
      ) : (
        <div className="mt-2 text-xs text-slate-500">No official diagram exists for this job.</div>
      )}
    </div>
  );
}

function ProjectInteractionPanel({ project, onUpdate }: { project: Project; onUpdate: (p: Project) => void }) {
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<ArrangementForm>(() => initialArrangementForm(project.bearingCodes));

  useEffect(() => {
    setShowForm(false);
    setEditingId(null);
  }, [project.id]);

  const startNew = () => {
    setForm(initialArrangementForm(project.bearingCodes));
    setEditingId(null);
    setShowForm(true);
  };

  const startEdit = (arr: SavedArrangement) => {
    // the server sends null for the detail blocks that do not apply to the saved type/component
    const empty = initialArrangementForm(project.bearingCodes);
    setForm({
      name: arr.name,
      material: arr.material,
      type: arr.type,
      slots: arr.slots,
      bsb: arr.bsb ?? empty.bsb,
      oa: arr.oa ?? empty.oa,
      component: arr.component,
      hasCenterLock: arr.hasCenterLock,
      freehub: arr.freehub ?? empty.freehub,
    });
    setEditingId(arr.id);
    setShowForm(true);
  };

  const saveArrangement = async () => {
    const payload = {
      project_id: project.id,
      name: form.name,
      material: form.material,
      type: form.type,
      slots: form.slots,
      component: form.component,
      has_center_lock: form.hasCenterLock,
      freehub: form.component === "freehub" ? { body: form.freehub.body, one_side: form.freehub.oneSide } : null,
      bsb: form.type === "BSB" ? {
        has_spacer: form.bsb.hasSpacer,
        spacer_len_ge_10mm: form.bsb.spacerLenGe10mm,
        spacer_mobility: form.bsb.spacerMobility,
      } : null,
      oa: form.type === "OA" ? { axle_length: form.oa.axleLength } : null,
    };
    const method = editingId ? "PUT" : "POST";
    const url = editingId ? `/arrangements/${editingId}` : "/arrangements";
    const res = await fetch(url, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    if (!res.ok) throw new Error(`Save failed (${res.status})`);
    const saved = await res.json();

    const savedArr: SavedArrangement = { id: saved.id, ...form };
    const nextArrs = editingId
      ? project.arrangements.map((a) => (a.id === editingId ? savedArr : a))
      : [...project.arrangements, savedArr];
    onUpdate({ ...project, arrangements: nextArrs });
    setShowForm(false);
    setEditingId(null);
  };

  return (
    <div className="lg:col-span-5 rounded-3xl border border-slate-200 bg-white p-4 shadow-sm flex flex-col">
      <div className="flex items-center justify-between pb-3 border-b border-slate-200">
        <h3 className="text-lg font-semibold">Arrangements</h3>
        <button className="px-3 py-1.5 rounded-xl bg-slate-900 text-white hover:bg-slate-800" onClick={startNew}>+ Add arrangement</button>
      </div>

      {!showForm && (
        <div className="mt-4">
          <BearingsFound project={project} />
          <div className="text-sm font-medium mb-2">Saved arrangements</div>
          {project.arrangements.length === 0 ? (
            <div className="text-sm text-slate-500">No arrangements yet. Click "Add arrangement" to start the questionnaire.</div>
          ) : (
            <div className="space-y-3">
              {project.arrangements.map((a) => (
                <div key={a.id} className="rounded-2xl border border-slate-200 p-3 hover:bg-slate-50">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="font-medium cursor-pointer" onClick={() => startEdit(a)}>{a.name}</div>
                      <div className="text-xs text-slate-500">
                        {a.type} • {formatSequence(a)}
                      </div>
                    </div>
                    <button className="text-sm px-3 py-1 rounded-xl border border-slate-300" onClick={() => startEdit(a)}>Edit</button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {showForm && (
        <ArrangementFormView
          form={form}
          allBearingCodes={project.bearingCodes}
          onChange={setForm}
          onCancel={() => { setShowForm(false); setEditingId(null); }}
          onSave={async () => { try { await saveArrangement(); } catch (e: any) { alert(e.message); } }}
        />
      )}
    </div>
  );
}

// The bearings read from the diagram, each with its size and where the code and the size come from.
function BearingsFound({ project }: { project: Project }) {
  const dimensionsLabel = { standard: "standard size", code: "size is in the code", web: "catalogue page" };
  return (
    <div className="mb-4">
      <div className="text-sm font-medium mb-2">Bearings found</div>
      {project.bearings.length === 0 && <div className="text-sm text-slate-500">No bearings were found in this diagram.</div>}
      <div className="space-y-2">
        {project.bearings.map((b) => (
          <div key={b.code} className="rounded-2xl border border-slate-200 p-3 text-sm">
            <div className="flex items-center justify-between gap-3">
              <span className="font-medium">{b.code}{b.quantity ? ` × ${b.quantity}` : ""}</span>
              {b.innerDiameter !== null ? (
                <span>{b.innerDiameter} × {b.outerDiameter} × {b.width} mm</span>
              ) : (
                <span className="text-amber-700">dimensions not found</span>
              )}
            </div>
            <div className="text-xs text-slate-500 mt-1">
              {b.foundIn === "diagram" ? "Code printed in the diagram" : "Code looked up from"}
              {b.reference ? (b.foundIn === "diagram" ? ` (label ${b.reference})` : ` ${b.reference}`) : ""}
              {b.sourceUrl && <> • <a className="underline" href={b.sourceUrl} target="_blank" rel="noreferrer">source</a></>}
              {b.dimensionsSource && <> • size: {dimensionsLabel[b.dimensionsSource]}</>}
              {b.dimensionsSourceUrl && <> (<a className="underline" href={b.dimensionsSourceUrl} target="_blank" rel="noreferrer">source</a>)</>}
            </div>
          </div>
        ))}
        {project.unresolvedReferences.map((r, i) => (
          <div key={i} className="rounded-2xl border border-amber-300 bg-amber-50 p-3 text-sm">
            <div className="font-medium">Not identified: {r.description}{r.part_number ? ` (part ${r.part_number})` : ""}</div>
            {r.note && <div className="text-xs text-slate-600 mt-1">{r.note}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}

// -------------------------------
// Arrangement form + helpers
// -------------------------------

function initialArrangementForm(allBearingCodes: string[]): ArrangementForm {
  return {
    name: "",
    material: null,
    type: null,
    slots: [],
    bsb: { hasSpacer: null, spacerLenGe10mm: null, spacerMobility: null },
    oa: { axleLength: null },
    component: null,
    hasCenterLock: null,
    freehub: { body: null, oneSide: null },
  };
}

function ArrangementFormView({ form, onChange, onSave, onCancel, allBearingCodes }: {
  form: ArrangementForm;
  onChange: (f: ArrangementForm) => void;
  onSave: () => void;
  onCancel: () => void;
  allBearingCodes: string[];
}) {
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try { await onSave(); } finally { setSaving(false); }
  };

  return (
    <div className="mt-4 space-y-4">
      <div className="flex items-center justify-between">
        <h4 className="font-medium">{form.name ? `Edit: ${form.name}` : "New arrangement"}</h4>
      </div>

      <div className="grid grid-cols-1 gap-4">
        <div>
          <label className="block text-sm font-medium mb-1">Arrangement name</label>
          <input className="w-full rounded-xl border border-slate-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-slate-900" placeholder="e.g., Main pivot" value={form.name} onChange={(e) => onChange({ ...form, name: e.target.value })} />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">Arrangement type</label>
          <div className="flex flex-wrap gap-2">
            {(["SP", "BSB", "OA"] as ArrangementType[]).map((t) => (
              <button key={t} type="button" className={clsx("px-3 py-1.5 rounded-xl border", form.type === t ? "bg-slate-900 text-white border-slate-900" : "border-slate-300 hover:bg-slate-50")} onClick={() => onChange({ ...form, type: t, slots: resizeSlots(form.slots, t) })}>
                {t === "SP" ? "Simple Pivot" : t === "BSB" ? "Bearing–Spacer–Bearing" : "Over‑Axle"}
              </button>
            ))}
          </div>
        </div>

        {form.type === "BSB" && (
          <div className="rounded-2xl border border-slate-200 p-3">
            <div className="text-sm font-medium mb-2">Spacer details</div>
            <RowBinary label="Is it with a spacer?" value={form.bsb.hasSpacer} onChange={(v) => onChange({ ...form, bsb: { hasSpacer: v, spacerLenGe10mm: null, spacerMobility: null } })} trueLabel="With" falseLabel="Without" />
            {form.bsb.hasSpacer === true && (
              <>
                <div className="mt-2">
                  <RowBinary label="Is the spacer at least 10 mm long?" value={form.bsb.spacerLenGe10mm} onChange={(v) => onChange({ ...form, bsb: { ...form.bsb, spacerLenGe10mm: v, spacerMobility: null } })} trueLabel="Yes" falseLabel="No" />
                </div>
                {form.bsb.spacerLenGe10mm === true && (
                  <div className="mt-2">
                    <RowChoices label="Does the spacer move or is it stuck?" value={form.bsb.spacerMobility} choices={["moves", "stuck"]} onChange={(v) => onChange({ ...form, bsb: { ...form.bsb, spacerMobility: v as SpacerMobility } })} />
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {form.type === "OA" && (
          <div className="rounded-2xl border border-slate-200 p-3">
            <RowChoices label="Is it a short or long axle?" value={form.oa.axleLength} choices={["short", "long"]} onChange={(v) => onChange({ ...form, oa: { axleLength: v as OAType } })} />
          </div>
        )}

        <div className="rounded-2xl border border-slate-200 p-3">
          <div className="flex items-center justify-between gap-4">
            <div className="text-sm">Select component</div>
            <div className="flex gap-2">
              {(["frame", "hub", "freehub"] as ComponentType[]).map((c) => (
                <button key={c} type="button" className={clsx("px-3 py-1.5 rounded-xl border", form.component === c ? "bg-slate-900 text-white border-slate-900" : "border-slate-300 hover:bg-slate-50")} onClick={() => onChange({ ...form, component: c, hasCenterLock: null, freehub: { body: null, oneSide: null } })}>
                  {c === "frame" ? "Frame" : c === "hub" ? "Hub" : "Freehub"}
                </button>
              ))}
            </div>
          </div>
          {form.component === "hub" && (
            <div className="mt-2">
              <RowBinary label="Does it have a center‑lock mount?" value={form.hasCenterLock} onChange={(v) => onChange({ ...form, hasCenterLock: v })} trueLabel="Yes" falseLabel="No" />
            </div>
          )}
          {form.component === "freehub" && (
            <>
              <div className="mt-2 flex items-center justify-between gap-4">
                <div className="text-sm">Which freehub body?</div>
                <div className="flex gap-2">
                  {(["hg_microspline", "xd_xdr"] as FreehubBody[]).map((b) => (
                    <button key={b} type="button" className={clsx("px-3 py-1.5 rounded-xl border", form.freehub.body === b ? "bg-slate-900 text-white border-slate-900" : "border-slate-300 hover:bg-slate-50")} onClick={() => onChange({ ...form, freehub: { ...form.freehub, body: b } })}>
                      {b === "hg_microspline" ? "HG / Microspline" : "XD / XDR"}
                    </button>
                  ))}
                </div>
              </div>
              <div className="mt-2">
                <RowBinary label="Are both bearings installed from the same side?" value={form.freehub.oneSide} onChange={(v) => onChange({ ...form, freehub: { ...form.freehub, oneSide: v } })} trueLabel="Yes" falseLabel="No" />
              </div>
            </>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">Bearing sequence</label>
          {form.type === null ? (
            <div className="text-sm text-slate-500">Select the arrangement type above first.</div>
          ) : allBearingCodes.length === 0 ? (
            <div className="text-sm text-slate-500">No bearings available for this project.</div>
          ) : (
            <BearingSequence form={form} allBearingCodes={allBearingCodes} onChange={(slots) => onChange({ ...form, slots })} />
          )}
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">Component material</label>
          <div className="flex gap-2">
            {(["carbon", "alloy"] as Material[]).map((m) => (
              <button key={m} type="button" className={clsx("px-3 py-1.5 rounded-xl border", form.material === m ? "bg-slate-900 text-white border-slate-900" : "border-slate-300 hover:bg-slate-50")} onClick={() => onChange({ ...form, material: m })}>{m}</button>
            ))}
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 pt-2">
          <button className="px-4 py-2 rounded-2xl border border-slate-300 hover:bg-slate-50" onClick={onCancel}>Cancel</button>
          <button className={clsx("px-4 py-2 rounded-2xl bg-slate-900 text-white", saving && "opacity-70 cursor-not-allowed")} onClick={handleSave} disabled={saving}>{saving ? <Spinner label="Saving…" /> : "Save arrangement"}</button>
        </div>
      </div>
    </div>
  );
}

// Left-to-right picture of the arrangement: one box per bearing seat, with what sits between them.
function BearingSequence({ form, allBearingCodes, onChange }: { form: ArrangementForm; allBearingCodes: string[]; onChange: (slots: string[][]) => void; }) {
  const labels = slotLabels(form.type, form.component);
  const between = form.type === "OA" ? "axle" : form.bsb.hasSpacer === false ? "no spacer" : "spacer";
  const setSlot = (i: number, codes: string[]) => onChange(form.slots.map((s, j) => (j === i ? codes : s)));

  return (
    <div className="flex items-stretch gap-2">
      {form.slots.map((codes, i) => (
        <React.Fragment key={i}>
          {i > 0 && <div className="self-center text-xs text-slate-500 whitespace-nowrap">– {between} –</div>}
          <div className={clsx("flex-1 min-w-0 rounded-2xl border p-2", codes.length > 1 ? "border-amber-300 bg-amber-50" : "border-slate-200")}>
            <div className="flex flex-wrap items-center justify-between gap-x-2 text-xs text-slate-500 mb-2">
              <span className="whitespace-nowrap">{labels[i]}</span>
              {codes.length > 1 && <span className="text-amber-700">double‑stacked</span>}
            </div>
            <div className="flex flex-wrap gap-2">
              {codes.map((code, k) => (
                <button key={k} type="button" className="px-3 py-1.5 rounded-xl border text-sm bg-slate-900 text-white border-slate-900" title="Remove this bearing" onClick={() => setSlot(i, codes.filter((_, n) => n !== k))}>{code} ✕</button>
              ))}
              {codes.length < MAX_STACK && (
                <select className="w-full rounded-xl border border-slate-300 px-2 py-1.5 text-sm" value="" onChange={(e) => e.target.value && setSlot(i, [...codes, e.target.value])}>
                  <option value="">{codes.length === 0 ? "+ Add bearing" : "+ Stack another bearing"}</option>
                  {allBearingCodes.map((code) => <option key={code} value={code}>{code}</option>)}
                </select>
              )}
            </div>
          </div>
        </React.Fragment>
      ))}
    </div>
  );
}

function RowBinary({ label, value, onChange, trueLabel = "Yes", falseLabel = "No" }: { label: string; value: boolean | null; onChange: (v: boolean) => void; trueLabel?: string; falseLabel?: string; }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div className="text-sm">{label}</div>
      <div className="flex gap-2">
        <button type="button" className={clsx("px-3 py-1.5 rounded-xl border", value === true ? "bg-slate-900 text-white border-slate-900" : "border-slate-300 hover:bg-slate-50")} onClick={() => onChange(true)}>{trueLabel}</button>
        <button type="button" className={clsx("px-3 py-1.5 rounded-xl border", value === false ? "bg-slate-900 text-white border-slate-900" : "border-slate-300 hover:bg-slate-50")} onClick={() => onChange(false)}>{falseLabel}</button>
      </div>
    </div>
  );
}

function RowChoices<T extends string>({ label, value, choices, onChange }: { label: string; value: T | null; choices: readonly T[]; onChange: (v: T) => void; }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div className="text-sm">{label}</div>
      <div className="flex gap-2">
        {choices.map((c) => (
          <button key={c} type="button" className={clsx("px-3 py-1.5 rounded-xl border", value === c ? "bg-slate-900 text-white border-slate-900" : "border-slate-300 hover:bg-slate-50")} onClick={() => onChange(c)}>{String(c)}</button>
        ))}
      </div>
    </div>
  );
}
