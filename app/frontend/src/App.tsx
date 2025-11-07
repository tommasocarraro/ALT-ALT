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

type PieceEntry = {
  piece: string;
  variant: string | null;
  quantity_sets: number;
  notes: string | null;
  bearing_code: string | null;
};

type PhaseBuckets = {
  LEVERAGE: PieceEntry[];
  PRESS: PieceEntry[];
  CENTER: PieceEntry[];
  CLEARANCE: PieceEntry[];
};

type ArrangementPiecesSuggestion = {
  arrangement_id: number;
  name: string;
  removal: PhaseBuckets;
  insertion: PhaseBuckets;
};

type ProjectSummaryRow = {
  piece: string;
  variant: string | null;
  function: "LEVERAGE"|"PRESS"|"CENTER"|"CLEARANCE";
  quantity_sets: number;
};

interface ArrangementBSBDetails {
  hasSpacer: boolean | null;
  spacerLenGe10mm: boolean | null;
  spacerMobility: SpacerMobility | null; // only if spacerLenGe10mm === true
}

interface ArrangementOADetails {
  axleLength: OAType | null;
}

interface ArrangementForm {
  name: string;
  material: Material | null;
  type: ArrangementType | null;
  selectedBearingCodes: string[]; // codes from bearings_saved
  doubleStackedCodes: string[]; // subset of selectedBearingCodes
  bsb: ArrangementBSBDetails;
  oa: ArrangementOADetails;
  isHub: boolean | null;
  hasCenterLock: boolean | null; // only if isHub === true
}

interface SavedArrangement extends ArrangementForm {
  id: string; // server id (string for simplicity)
}

interface Project {
  id: number;
  title: string;
  diagramUrl: string;
  pdfUrl: string; // browser-servable URL for the PDF
  bearingCodes: string[];
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
  const [suggestions, setSuggestions] = useState<ArrangementPiecesSuggestion[] | null>(null);
  const [summary, setSummary] = useState<ProjectSummaryRow[] | null>(null);
  const [refreshKey, setRefreshKey] = useState(0); // bump to refetch after saves

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
          arrangements: p.arrangements || [],
        };
        setProject(mapped);
      } catch (e: any) { setError(e.message); }
    })();
  }, [id]);

  useEffect(() => {
    if (!project) return;
    (async () => {
      try {
        const [sugRes, sumRes] = await Promise.all([
          fetch(`/projects/${project.id}/pieces_suggestions`),
          fetch(`/projects/${project.id}/pieces_summary`),
        ]);
        if (!sugRes.ok) throw new Error("Failed to load suggestions");
        if (!sumRes.ok) throw new Error("Failed to load summary");
        setSuggestions(await sugRes.json());
        setSummary(await sumRes.json());
      } catch (e) {
        console.error(e);
        setSuggestions([]);
        setSummary([]);
      }
    })();
  }, [project, refreshKey]);

  if (error) return <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-red-700">{error}</div>;
  if (!project) return <div className="text-slate-600">Loading workspace…</div>;

  return (
    <ProjectWorkspace
      project={project}
      onBack={() => navigate("/")}
      onUpdate={(p) => { setProject(p); setRefreshKey(k => k+1); }}
      suggestions={suggestions}
      summary={summary}
      onRefetch={() => setRefreshKey(k => k+1)}
    />
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

function ProjectWorkspace({ project, onBack, onUpdate, suggestions, summary, onRefetch }:
  { project: Project; onBack: () => void; onUpdate: (p: Project) => void;
    suggestions: ArrangementPiecesSuggestion[] | null;
    summary: ProjectSummaryRow[] | null;
    onRefetch: () => void }) {
  const [numPages, setNumPages] = useState<number | null>(null);
  const [page, setPage] = useState(1);
  const [scale, setScale] = useState(1.2);

  const canPrev = page > 1;
  const canNext = numPages ? page < numPages : false;

  return (
    <>
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
        <div className="relative overflow-auto max-h-[75vh] py-3">
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
      <ProjectInteractionPanel project={project} onUpdate={onUpdate} onRefetch={onRefetch} />
    </div>

    <div className="mt-8 space-y-8 w-full">
      <div className="mt-6 space-y-4">
        <h3 className="text-lg font-semibold">Suggested pieces by arrangement</h3>
        {(!suggestions || suggestions.length === 0) ? (
          <div className="text-sm text-slate-500">No suggestions yet.</div>
        ) : (
          suggestions.map(sug => (
            <div key={sug.arrangement_id} className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="flex items-center justify-between mb-2">
                <div className="font-medium">{sug.name}</div>
                <div className="text-xs text-slate-500">Arrangement #{sug.arrangement_id}</div>
              </div>

              <div className="grid md:grid-cols-2 gap-4">
                {/* Removal */}
                <div>
                  <div className="text-sm font-medium mb-2">REMOVE</div>
                  <PhaseGroupBuckets buckets={sug.removal} />
                </div>

                {/* Insertion */}
                <div>
                  <div className="text-sm font-medium mb-2">INSERT</div>
                  <PhaseGroupBuckets buckets={sug.insertion} />
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      <div className="h-px bg-slate-200 my-6" />

      <div className="mt-6">
        <h3 className="text-lg font-semibold">Project pieces (deduped)</h3>
        {!summary || summary.length === 0 ? (
          <div className="text-sm text-slate-500">No pieces yet.</div>
        ) : (
          <div className="overflow-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="text-left border-b">
                  <th className="py-2 pr-4">Piece</th>
                  <th className="py-2 pr-4">Qty (sets)</th>
                </tr>
              </thead>
              <tbody>
                {summary.map((r, i) => (
                  <tr key={i} className="border-b last:border-0">
                    <td className="py-2 pr-4">{r.variant || "—"}</td>
                    <td className="py-2 pr-4">{r.quantity_sets}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
    </>
  );
}

function ProjectInteractionPanel({ project, onUpdate, onRefetch }:
  { project: Project; onUpdate: (p: Project) => void; onRefetch: () => void }) {
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
    setForm({
      name: arr.name,
      material: arr.material,
      type: arr.type,
      selectedBearingCodes: arr.selectedBearingCodes,
      doubleStackedCodes: arr.doubleStackedCodes,
      bsb: arr.bsb,
      oa: arr.oa,
      isHub: arr.isHub,
      hasCenterLock: arr.hasCenterLock,
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
      selected_bearing_codes: form.selectedBearingCodes,
      double_stacked_codes: form.doubleStackedCodes,
      is_hub: form.isHub,
      has_center_lock: form.hasCenterLock,
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
    onRefetch();
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
                        {a.type} • {a.selectedBearingCodes.join(", ")}
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

// -------------------------------
// Arrangement form + helpers
// -------------------------------

function initialArrangementForm(allBearingCodes: string[]): ArrangementForm {
  return {
    name: "",
    material: null,
    type: null,
    selectedBearingCodes: [],
    doubleStackedCodes: [],
    bsb: { hasSpacer: null, spacerLenGe10mm: null, spacerMobility: null },
    oa: { axleLength: null },
    isHub: null,
    hasCenterLock: null,
  };
}

function PhaseGroupBuckets({ buckets }: { buckets: PhaseBuckets }) {
  const order: Array<keyof PhaseBuckets> = ["LEVERAGE","PRESS","CENTER","CLEARANCE"];
  const label: Record<keyof PhaseBuckets, string> = {
    LEVERAGE: "LEVERAGE", PRESS: "PRESS", CENTER: "CENTER",
    CLEARANCE: "CLEARANCE"
  };

  return (
    <div className="space-y-3">
      {order.map(k => {
        const items = buckets[k];
        if (!items || items.length === 0) return null;
        return (
          <div key={k}>
            <div className="text-xs font-semibold tracking-wide text-slate-600 mb-1">{label[k]}</div>
            <ul className="space-y-1">
              {items.map((it, idx) => (
                <li key={idx} className="text-sm">
                  {it.variant ? <span>{it.variant}</span> : null}
                  {it.quantity_sets > 1 ? <span className="ml-1 text-slate-500">(×{it.quantity_sets})</span> : null}
                  {it.bearing_code ? <span className="ml-1 text-slate-400">[{it.bearing_code}]</span> : null}
                  {it.notes ? <span className="ml-1 text-slate-400">• {it.notes}</span> : null}
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}

function ArrangementFormView({ form, onChange, onSave, onCancel, allBearingCodes }: {
  form: ArrangementForm;
  onChange: (f: ArrangementForm) => void;
  onSave: () => void;
  onCancel: () => void;
  allBearingCodes: string[];
}) {
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    onChange({ ...form, doubleStackedCodes: form.doubleStackedCodes.filter((c) => form.selectedBearingCodes.includes(c)) });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.selectedBearingCodes.join(",")]);

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
          <label className="block text-sm font-medium mb-1">Select bearings</label>
          {allBearingCodes.length === 0 ? (
            <div className="text-sm text-slate-500">No bearings available for this project.</div>
          ) : (
            <div className="flex flex-wrap gap-2">
              {allBearingCodes.map((code) => {
                const selected = form.selectedBearingCodes.includes(code);
                return (
                  <button type="button" key={code} className={clsx("px-3 py-1.5 rounded-xl border text-sm", selected ? "bg-slate-900 text-white border-slate-900" : "border-slate-300 hover:bg-slate-50")} onClick={() => {
                    const set = new Set(form.selectedBearingCodes);
                    selected ? set.delete(code) : set.add(code);
                    onChange({ ...form, selectedBearingCodes: Array.from(set) });
                  }}>{code}</button>
                );
              })}
            </div>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">Arrangement type</label>
          <div className="flex flex-wrap gap-2">
            {(["SP", "BSB", "OA"] as ArrangementType[]).map((t) => (
              <button key={t} type="button" className={clsx("px-3 py-1.5 rounded-xl border", form.type === t ? "bg-slate-900 text-white border-slate-900" : "border-slate-300 hover:bg-slate-50")} onClick={() => onChange({ ...form, type: t })}>
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

        <div>
          <label className="block text-sm font-medium mb-1">Any double‑stacked bearings?</label>
          {form.selectedBearingCodes.length === 0 ? (
            <div className="text-sm text-slate-500">Select bearings above first.</div>
          ) : (
            <div className="flex flex-wrap gap-2">
              {form.selectedBearingCodes.map((code) => {
                const active = form.doubleStackedCodes.includes(code);
                return (
                  <button key={code} type="button" className={clsx("px-3 py-1.5 rounded-xl border text-sm", active ? "bg-amber-100 border-amber-300" : "border-slate-300 hover:bg-slate-50")} onClick={() => {
                    const set = new Set(form.doubleStackedCodes);
                    active ? set.delete(code) : set.add(code);
                    onChange({ ...form, doubleStackedCodes: Array.from(set) });
                  }} title="Toggle double-stacked for this bearing">{active ? `⟡ ${code}` : code}</button>
                );
              })}
            </div>
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

        <div className="rounded-2xl border border-slate-200 p-3">
          <RowBinary label="Is the component a hub?" value={form.isHub} onChange={(v) => onChange({ ...form, isHub: v, hasCenterLock: null })} trueLabel="Yes" falseLabel="No" />
          {form.isHub === true && (
            <div className="mt-2">
              <RowBinary label="Does it have a center‑lock mount?" value={form.hasCenterLock} onChange={(v) => onChange({ ...form, hasCenterLock: v })} trueLabel="Yes" falseLabel="No" />
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 pt-2">
          <button className="px-4 py-2 rounded-2xl border border-slate-300 hover:bg-slate-50" onClick={onCancel}>Cancel</button>
          <button className={clsx("px-4 py-2 rounded-2xl bg-slate-900 text-white", saving && "opacity-70 cursor-not-allowed")} onClick={handleSave} disabled={saving}>{saving ? <Spinner label="Saving…" /> : "Save arrangement"}</button>
        </div>
      </div>
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
