import { useState, useRef, useCallback } from 'react';
import {
  X, Upload, CheckCircle, AlertCircle, Loader2, FileText, Star,
} from 'lucide-react';
import { api } from '../api';
import type { UploadResult, ReviewField } from '../types';

type ModalState = 'idle' | 'uploading' | 'review' | 'saving' | 'done' | 'error';

interface Props {
  onClose: () => void;
  /** Called after successful confirm – parent should refresh dashboard data */
  onDone: () => void;
}

const DOC_TYPE_LABELS: Record<string, string> = {
  utility_bill:      'Utility Bill',
  delivery_receipt:  'Delivery / Shipment',
  invoice:           'Invoice',
  receipt:           'Receipt',
  unknown:           'Document',
};

function FieldRow({ field, value, onChange }: {
  field: ReviewField;
  value: string;
  onChange: (key: string, val: string) => void;
}) {
  const isEditable = field.editable;
  return (
    <div className={`flex items-center gap-3 px-4 py-3 rounded-xl transition-colors ${
      isEditable ? 'bg-emerald-50 border border-emerald-200' : 'bg-slate-50 border border-transparent'
    }`}>
      <div className="w-40 shrink-0">
        <span className="text-xs font-semibold text-slate-500 flex items-center gap-1">
          {isEditable && <Star size={10} className="text-emerald-500 fill-emerald-500" />}
          {field.label}
        </span>
      </div>
      {isEditable ? (
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(field.key, e.target.value)}
          className="flex-1 text-sm font-semibold text-slate-800 bg-white border border-emerald-300 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-emerald-400"
        />
      ) : (
        <span className="flex-1 text-sm text-slate-700 font-medium">
          {value || <span className="text-slate-400 italic">not detected</span>}
        </span>
      )}
    </div>
  );
}

export default function UploadModal({ onClose, onDone }: Props) {
  const [state, setState] = useState<ModalState>('idle');
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [review, setReview] = useState<UploadResult | null>(null);
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const setReviewState = useCallback((result: UploadResult) => {
    const vals: Record<string, string> = {};
    for (const f of result.fields) vals[f.key] = f.value != null ? String(f.value) : '';
    setReview(result);
    setFieldValues(vals);
    setState('review');
  }, []);

  const handleFileSelected = (selected: File) => {
    setFile(selected);
    setErrorMsg(null);
  };

  const handleUpload = async () => {
    if (!file) return;
    setState('uploading');
    try {
      const result = await api.upload(file);
      setReviewState(result);
    } catch (e) {
      setErrorMsg((e as Error).message);
      setState('error');
    }
  };

  const handleConfirm = async () => {
    if (!review) return;
    setState('saving');
    try {
      await api.confirm({
        doc_type: review.doc_type,
        fields: fieldValues,
        filename: file?.name ?? '',
      });
      setState('done');
    } catch (e) {
      setErrorMsg((e as Error).message);
      setState('error');
    }
  };

  const handleDone = () => {
    onDone();   // triggers dashboard refresh in parent
    onClose();
  };

  // ── Drop zone handlers ────────────────────────────────────────────────────
  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) handleFileSelected(dropped);
  };

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    /* Backdrop */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(15,23,42,0.55)', backdropFilter: 'blur(4px)' }}
      onClick={(e) => e.target === e.currentTarget && state === 'idle' && onClose()}
    >
      {/* Modal card */}
      <div
        className="w-full max-w-lg rounded-2xl flex flex-col overflow-hidden"
        style={{
          background: 'var(--color-card, #fff)',
          boxShadow: '0 24px 64px -12px rgba(15,23,42,0.28)',
          border: '1px solid rgba(15,23,42,0.08)',
          maxHeight: '90vh',
        }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <div className="flex items-center gap-3">
            <div
              className="w-8 h-8 rounded-lg flex items-center justify-center"
              style={{ background: 'linear-gradient(135deg, #059669 0%, #10b981 100%)' }}
            >
              <FileText size={15} color="white" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-slate-800">Add Document</h2>
              <p className="text-xs text-slate-400">
                {state === 'idle' && 'Upload a bill, invoice or shipment record'}
                {state === 'uploading' && 'Extracting fields with Document AI…'}
                {state === 'review' && `Verify extracted fields · ${DOC_TYPE_LABELS[review?.doc_type ?? ''] ?? 'Document'}`}
                {state === 'saving' && 'Saving & recalculating emissions…'}
                {state === 'done' && 'Document saved successfully'}
                {state === 'error' && 'Something went wrong'}
              </p>
            </div>
          </div>
          {state !== 'saving' && (
            <button
              onClick={onClose}
              className="w-8 h-8 rounded-lg flex items-center justify-center text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
            >
              <X size={16} />
            </button>
          )}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5">

          {/* ── STATE: idle ─────────────────────────────────────────────── */}
          {state === 'idle' && (
            <div className="flex flex-col gap-4">
              <div
                className={`rounded-xl border-2 border-dashed flex flex-col items-center justify-center gap-3 py-10 cursor-pointer transition-colors ${
                  dragOver
                    ? 'border-emerald-400 bg-emerald-50'
                    : file
                    ? 'border-emerald-300 bg-emerald-50/50'
                    : 'border-slate-200 hover:border-slate-300 bg-slate-50'
                }`}
                onClick={() => fileRef.current?.click()}
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={onDrop}
              >
                <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${file ? 'bg-emerald-100' : 'bg-slate-100'}`}>
                  <Upload size={22} className={file ? 'text-emerald-600' : 'text-slate-400'} />
                </div>
                {file ? (
                  <div className="text-center">
                    <p className="text-sm font-semibold text-emerald-700">{file.name}</p>
                    <p className="text-xs text-slate-400 mt-0.5">{(file.size / 1024).toFixed(1)} KB · click to change</p>
                  </div>
                ) : (
                  <div className="text-center">
                    <p className="text-sm font-semibold text-slate-700">Drop a file or click to browse</p>
                    <p className="text-xs text-slate-400 mt-0.5">PDF, JPG, PNG supported</p>
                  </div>
                )}
              </div>
              <input
                ref={fileRef}
                type="file"
                accept=".pdf,.jpg,.jpeg,.png,.tiff,.tif,.webp"
                className="hidden"
                onChange={(e) => e.target.files?.[0] && handleFileSelected(e.target.files[0])}
              />
            </div>
          )}

          {/* ── STATE: uploading ─────────────────────────────────────────── */}
          {state === 'uploading' && (
            <div className="flex flex-col items-center justify-center gap-4 py-10">
              <Loader2 size={40} className="text-emerald-500 animate-spin" />
              <div className="text-center">
                <p className="text-sm font-semibold text-slate-700">Running Document AI…</p>
                <p className="text-xs text-slate-400 mt-1">OCR → classify → Gemini extraction</p>
              </div>
            </div>
          )}

          {/* ── STATE: review ────────────────────────────────────────────── */}
          {state === 'review' && review && (
            <div className="flex flex-col gap-3">
              <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 flex items-start gap-2">
                <Star size={14} className="text-amber-500 fill-amber-400 mt-0.5 shrink-0" />
                <p className="text-xs text-amber-700">
                  All fields are editable. If anything was misdetected, correct it here before saving.
                </p>
              </div>
              <div className="flex flex-col gap-2">
                {review.fields.map((field) => (
                  <FieldRow
                    key={field.key}
                    field={field}
                    value={fieldValues[field.key] ?? ''}
                    onChange={(key, val) => setFieldValues((prev) => ({ ...prev, [key]: val }))}
                  />
                ))}
              </div>
              {review.warnings.length > 0 && (
                <div className="bg-rose-50 border border-rose-200 rounded-xl px-4 py-3">
                  <p className="text-xs font-semibold text-rose-600 mb-1">Extraction warnings</p>
                  {review.warnings.map((w, i) => (
                    <p key={i} className="text-xs text-rose-500">{w}</p>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ── STATE: saving ────────────────────────────────────────────── */}
          {state === 'saving' && (
            <div className="flex flex-col items-center justify-center gap-4 py-10">
              <Loader2 size={40} className="text-emerald-500 animate-spin" />
              <div className="text-center">
                <p className="text-sm font-semibold text-slate-700">Saving document…</p>
                <p className="text-xs text-slate-400 mt-1">Writing to DB and recalculating emissions</p>
              </div>
            </div>
          )}

          {/* ── STATE: done ──────────────────────────────────────────────── */}
          {state === 'done' && (
            <div className="flex flex-col items-center justify-center gap-4 py-10">
              <div className="w-14 h-14 rounded-2xl bg-emerald-100 flex items-center justify-center">
                <CheckCircle size={30} className="text-emerald-600" />
              </div>
              <div className="text-center">
                <p className="text-sm font-bold text-slate-800">Document saved!</p>
                <p className="text-xs text-slate-400 mt-1">
                  Emissions have been recalculated. Dashboard will refresh.
                </p>
              </div>
            </div>
          )}

          {/* ── STATE: error ─────────────────────────────────────────────── */}
          {state === 'error' && (
            <div className="flex flex-col items-center justify-center gap-4 py-10">
              <div className="w-14 h-14 rounded-2xl bg-rose-100 flex items-center justify-center">
                <AlertCircle size={30} className="text-rose-500" />
              </div>
              <div className="text-center">
                <p className="text-sm font-bold text-slate-800">Something went wrong</p>
                <p className="text-xs text-rose-500 mt-1 max-w-xs">{errorMsg}</p>
              </div>
            </div>
          )}
        </div>

        {/* Footer actions */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-slate-100 bg-slate-50/60">
          {/* Left */}
          <div>
            {state === 'review' && (
              <button
                onClick={() => setState('idle')}
                className="text-sm text-slate-500 hover:text-slate-700 font-medium transition-colors"
              >
                ← Back
              </button>
            )}
            {state === 'error' && (
              <button
                onClick={() => { setState('idle'); setErrorMsg(null); }}
                className="text-sm text-slate-500 hover:text-slate-700 font-medium transition-colors"
              >
                ← Try again
              </button>
            )}
          </div>

          {/* Right */}
          <div className="flex items-center gap-2">
            {(state === 'idle' || state === 'error') && (
              <button
                onClick={onClose}
                className="px-4 py-2 text-sm font-medium text-slate-600 rounded-xl hover:bg-slate-200 transition-colors"
              >
                Cancel
              </button>
            )}

            {state === 'idle' && (
              <button
                onClick={handleUpload}
                disabled={!file}
                className="px-5 py-2 text-sm font-semibold text-white rounded-xl transition-all disabled:opacity-40 disabled:cursor-not-allowed hover:opacity-90 active:scale-95"
                style={{ background: 'linear-gradient(135deg, #059669 0%, #10b981 100%)' }}
              >
                Upload & Analyse
              </button>
            )}

            {state === 'review' && (
              <button
                onClick={handleConfirm}
                className="px-5 py-2 text-sm font-semibold text-white rounded-xl hover:opacity-90 active:scale-95 transition-all"
                style={{ background: 'linear-gradient(135deg, #059669 0%, #10b981 100%)' }}
              >
                Confirm & Save
              </button>
            )}

            {state === 'done' && (
              <button
                onClick={handleDone}
                className="px-5 py-2 text-sm font-semibold text-white rounded-xl hover:opacity-90 active:scale-95 transition-all"
                style={{ background: 'linear-gradient(135deg, #059669 0%, #10b981 100%)' }}
              >
                Back to Dashboard
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
