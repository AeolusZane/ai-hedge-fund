import { useState, useEffect } from 'react';
import { ChevronRight, ChevronDown, File, Folder, FolderOpen, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

interface FileEntry {
  name: string;
  path: string;
  type: 'file' | 'dir';
  size: number | null;
}

interface WorkspaceFilesResponse {
  path: string;
  entries: FileEntry[];
  error?: string;
}

interface FileContentResponse {
  path: string;
  content?: string;
  size?: number;
  encoding?: string;
  error?: string;
}

interface WorkspaceBrowserProps {
  domain: string;
  runId: number;
  isOpen: boolean;
  onClose: () => void;
}

export function WorkspaceBrowser({ domain, runId, isOpen, onClose }: WorkspaceBrowserProps) {
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(new Set());
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen && runId) {
      loadFiles('/');
    }
  }, [isOpen, runId]);

  const loadFiles = async (path: string) => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(
        `${API_BASE_URL}/workflows/${domain}/workspace/${runId}/files?path=${encodeURIComponent(path)}&max_depth=3`
      );
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data: WorkspaceFilesResponse = await response.json();
      if (data.error) {
        setError(data.error);
      } else {
        setFiles(data.entries);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load files');
    } finally {
      setLoading(false);
    }
  };

  const loadFileContent = async (path: string) => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(
        `${API_BASE_URL}/workflows/${domain}/workspace/${runId}/file?path=${encodeURIComponent(path)}`
      );
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data: FileContentResponse = await response.json();
      if (data.error) {
        setError(data.error);
      } else {
        setFileContent(data.content || '');
        setSelectedFile(path);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load file');
    } finally {
      setLoading(false);
    }
  };

  const toggleDir = (path: string) => {
    const newExpanded = new Set(expandedDirs);
    if (newExpanded.has(path)) {
      newExpanded.delete(path);
    } else {
      newExpanded.add(path);
    }
    setExpandedDirs(newExpanded);
  };

  const formatSize = (bytes: number | null): string => {
    if (bytes === null) return '';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const renderFileTree = (entries: FileEntry[], depth: number = 0) => {
    return entries.map((entry) => {
      const isExpanded = expandedDirs.has(entry.path);
      const isSelected = selectedFile === entry.path;

      return (
        <div key={entry.path}>
          <div
            className={cn(
              'flex items-center gap-1 px-2 py-1 hover:bg-muted/50 cursor-pointer text-sm',
              isSelected && 'bg-blue-500/10 text-blue-600'
            )}
            style={{ paddingLeft: `${depth * 16 + 8}px` }}
            onClick={() => {
              if (entry.type === 'dir') {
                toggleDir(entry.path);
              } else {
                loadFileContent(entry.path);
              }
            }}
          >
            {entry.type === 'dir' ? (
              <>
                {isExpanded ? (
                  <ChevronDown className="h-4 w-4 shrink-0" />
                ) : (
                  <ChevronRight className="h-4 w-4 shrink-0" />
                )}
                {isExpanded ? (
                  <FolderOpen className="h-4 w-4 shrink-0 text-blue-500" />
                ) : (
                  <Folder className="h-4 w-4 shrink-0 text-blue-500" />
                )}
              </>
            ) : (
              <>
                <span className="w-4" />
                <File className="h-4 w-4 shrink-0 text-muted-foreground" />
              </>
            )}
            <span className="truncate flex-1">{entry.name}</span>
            {entry.type === 'file' && entry.size !== null && (
              <span className="text-xs text-muted-foreground">{formatSize(entry.size)}</span>
            )}
          </div>
          {entry.type === 'dir' && isExpanded && (
            <div>{renderFileTree(entries.filter(e => e.path.startsWith(entry.path + '/')), depth + 1)}</div>
          )}
        </div>
      );
    });
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-background border rounded-lg shadow-lg w-[90vw] max-w-6xl h-[80vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b">
          <h2 className="text-lg font-semibold">Workspace Files (Run #{runId})</h2>
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        {/* Content */}
        <div className="flex-1 flex overflow-hidden">
          {/* File Tree */}
          <div className="w-80 border-r overflow-hidden flex flex-col">
            <div className="px-3 py-2 text-sm font-medium border-b bg-muted/30">Files</div>
            <div className="flex-1 overflow-y-auto">
              {loading && files.length === 0 ? (
                <div className="p-4 text-sm text-muted-foreground">Loading...</div>
              ) : error ? (
                <div className="p-4 text-sm text-red-500">{error}</div>
              ) : files.length === 0 ? (
                <div className="p-4 text-sm text-muted-foreground">No files found</div>
              ) : (
                <div className="py-2">{renderFileTree(files)}</div>
              )}
            </div>
          </div>

          {/* File Content */}
          <div className="flex-1 overflow-hidden flex flex-col">
            {selectedFile ? (
              <>
                <div className="px-3 py-2 text-sm font-medium border-b bg-muted/30 flex items-center justify-between">
                  <span className="truncate">{selectedFile}</span>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setSelectedFile(null);
                      setFileContent(null);
                    }}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
                <div className="flex-1 overflow-y-auto">
                  <pre className="p-4 text-xs font-mono whitespace-pre-wrap break-words">
                    {fileContent || 'Loading...'}
                  </pre>
                </div>
              </>
            ) : (
              <div className="flex-1 flex items-center justify-center text-sm text-muted-foreground">
                Select a file to view its contents
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
