import { FileText } from 'lucide-react';
import type { DocumentSource } from '../types';

interface Props {
  documents: DocumentSource[];
  loading?: boolean;
  title?: string;
  subtitle?: string;
}

function formatDate(iso: string) {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
  } catch {
    return iso;
  }
}

function formatType(type: string) {
  return type.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function DataSourcesList({ documents, loading, title = 'Data sources', subtitle = 'Documents used for metrics' }: Props) {
  return (
    <div className="rounded-2xl p-5 flex flex-col h-full" style={{ background: 'var(--color-card)', boxShadow: 'var(--shadow-card)' }}>
      <div className="flex items-center gap-2 mb-4">
        <div className="w-8 h-8 rounded-xl flex items-center justify-center" style={{ background: 'var(--chart-primary)' }}>
          <FileText size={16} color="white" />
        </div>
        <div>
          <h3 className="text-sm font-bold uppercase tracking-widest opacity-80" style={{ color: 'var(--color-text)' }}>
            {title}
          </h3>
          <p className="text-xs opacity-70" style={{ color: 'var(--color-text)' }}>
            {subtitle}
          </p>
        </div>
      </div>
      {loading ? (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-12 rounded-lg animate-pulse opacity-60" style={{ background: 'var(--color-card-outline)' }} />
          ))}
        </div>
      ) : !documents.length ? (
        <p className="text-sm opacity-70" style={{ color: 'var(--color-text)' }}>No documents yet</p>
      ) : (
        <ul className="space-y-1.5 overflow-y-auto max-h-[320px] pr-1">
          {documents.map((doc) => (
            <li
              key={doc.document_id}
              className="flex items-center gap-3 py-2 px-3 rounded-xl text-sm border"
              style={{ borderColor: 'var(--color-card-outline)', color: 'var(--color-text)' }}
            >
              <span className="shrink-0 px-2 py-0.5 rounded-md text-xs font-medium opacity-80" style={{ background: 'rgba(5, 74, 41, 0.12)' }}>
                {formatType(doc.document_type)}
              </span>
              <span className="truncate flex-1 min-w-0" title={doc.source_filename}>
                {doc.source_filename || `Document #${doc.document_id}`}
              </span>
              <span className="text-xs opacity-60 shrink-0">{formatDate(doc.created_at)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
