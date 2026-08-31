import { useState } from "react";
import * as api from "../api/client.js";
import LoadingChecklist, { ANALYZE_STEPS } from "./LoadingChecklist.jsx";

export default function UploadZone({ onUpload, busy, setBusy, setErr }) {
  const [dragOver, setDragOver] = useState(false);

  const handleChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    await doUpload(file);
  };

  const doUpload = async (file) => {
    setBusy(true); setErr(null);
    try {
      const res = await api.uploadFile(file);
      onUpload(res);
    } catch (e) {
      setErr(e.message || "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  const onDrop = async (e) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) await doUpload(file);
  };

  if (busy) {
    return (
      <LoadingChecklist steps={ANALYZE_STEPS} title="Analyzing your resume" />
    );
  }

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={onDrop}
      className={`card border-2 border-dashed p-12 text-center transition-all
                  duration-200 animate-fadeUp
                  ${dragOver ? "border-primary bg-primary/5 shadow-glow"
                             : "border-line hover:border-faint"}`}
    >
      <input type="file" accept=".pdf,.docx,.doc" onChange={handleChange}
             className="hidden" id="file-input" />
      <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center
                      rounded-md bg-primary/10 border border-primary/30
                      text-primary text-2xl">
        ↑
      </div>
      <label htmlFor="file-input"
             className="cursor-pointer text-lg font-semibold text-ink
                        hover:text-primary transition-colors">
        Drop your resume here, or <span className="text-primary">browse</span>
      </label>
      <p className="text-sm text-mute mt-2">
        PDF or Word (.docx / .doc) · Max 10MB
      </p>
      <p className="text-xs text-faint mt-4">
        You&apos;ll get an ATS + visual diagnosis, a red-flag scan and a clean
        one-page rebuild.
      </p>
    </div>
  );
}

