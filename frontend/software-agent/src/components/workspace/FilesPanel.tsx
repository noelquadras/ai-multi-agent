"use client";

import { useState } from "react";
import { useQuery, useMutation } from "convex/react";
import { api } from "../../../convex/_generated/api";
import { Id } from "../../../convex/_generated/dataModel";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Folder,
  File,
  FileCode,
  FileText,
  Upload,
  Download,
  Trash2,
  Plus,
  RefreshCw,
  Loader2,
} from "lucide-react";

interface FilesPanelProps {
  projectId?: Id<"projects">;
  userId?: string;
  onFileSelect?: (content: string, filename: string) => void;
}

export function FilesPanel({ projectId, userId, onFileSelect }: FilesPanelProps) {
  const [isUploading, setIsUploading] = useState(false);
  
  // Query files from Convex (only if projectId is provided)
  const files = projectId 
    ? useQuery(api.files.getProjectFiles, { projectId })
    : [];

  // Mutations
  const createTextFile = useMutation(api.files.createTextFile);
  const deleteFile = useMutation(api.files.deleteFile);
  const generateUploadUrl = useMutation(api.files.generateUploadUrl);

  const getFileIcon = (filename: string) => {
    if (filename.endsWith(".py")) return <FileCode className="w-4 h-4 text-blue-400" />;
    if (filename.endsWith(".js") || filename.endsWith(".ts"))
      return <FileCode className="w-4 h-4 text-yellow-400" />;
    if (filename.endsWith(".md")) return <FileText className="w-4 h-4 text-cyan-400" />;
    return <File className="w-4 h-4 text-zinc-400" />;
  };

  const handleSaveFile = async (name: string, content: string) => {
    if (!projectId || !userId) return;
    
    await createTextFile({
      projectId,
      userId,
      name,
      path: `/${name}`,
      type: "code",
      content,
      isGenerated: true,
    });
  };

  const handleDeleteFile = async (fileId: Id<"files">) => {
    if (confirm("Are you sure you want to delete this file?")) {
      await deleteFile({ fileId });
    }
  };

  const handleFileClick = (file: { content?: string | null; name: string }) => {
    if (file.content && onFileSelect) {
      onFileSelect(file.content, file.name);
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const formatDate = (timestamp: number) => {
    return new Date(timestamp).toLocaleDateString();
  };

  if (!projectId) {
    return (
      <div className="w-64 h-full bg-[#0A0A0A] border-r border-[#1F1F1F] flex flex-col">
        <div className="p-4 border-b border-[#1F1F1F]">
          <div className="flex items-center gap-2">
            <Folder className="w-4 h-4 text-purple-400" />
            <h3 className="text-sm font-semibold text-zinc-300">Files</h3>
          </div>
        </div>
        <div className="flex-1 flex items-center justify-center p-4">
          <p className="text-xs text-zinc-500 text-center">
            Select or create a project to manage files
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="w-64 h-full bg-[#0A0A0A] border-r border-[#1F1F1F] flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-[#1F1F1F]">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Folder className="w-4 h-4 text-purple-400" />
            <h3 className="text-sm font-semibold text-zinc-300">Files</h3>
          </div>
          <Badge variant="outline" className="text-[10px] border-zinc-700">
            {files?.length || 0}
          </Badge>
        </div>
        
        <div className="flex gap-2">
          <Button
            variant="ghost"
            size="sm"
            className="flex-1 text-xs h-7 bg-[#141414] hover:bg-[#1F1F1F]"
            onClick={() => {
              const name = prompt("Enter file name:");
              if (name) handleSaveFile(name, "# New file\n");
            }}
          >
            <Plus className="w-3 h-3 mr-1" />
            New
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 bg-[#141414] hover:bg-[#1F1F1F]"
          >
            <Upload className="w-3 h-3" />
          </Button>
        </div>
      </div>

      {/* File List */}
      <div className="flex-1 overflow-auto">
        {!files || files.length === 0 ? (
          <div className="p-4 text-center">
            <File className="w-8 h-8 text-zinc-700 mx-auto mb-2" />
            <p className="text-xs text-zinc-500">No files yet</p>
            <p className="text-xs text-zinc-600 mt-1">
              Files will appear here after code generation
            </p>
          </div>
        ) : (
          <div className="p-2 space-y-1">
            {files.map((file) => (
              <div
                key={file._id}
                className="group flex items-center justify-between p-2 rounded-lg hover:bg-[#141414] cursor-pointer transition-colors"
                onClick={() => handleFileClick(file)}
              >
                <div className="flex items-center gap-2 min-w-0">
                  {getFileIcon(file.name)}
                  <div className="min-w-0">
                    <p className="text-sm text-zinc-300 truncate">{file.name}</p>
                    <p className="text-[10px] text-zinc-600">
                      {formatSize(file.size)} • {formatDate(file.updatedAt)}
                    </p>
                  </div>
                </div>
                
                <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  {file.isGenerated && (
                    <Badge className="text-[8px] px-1 py-0 bg-purple-500/20 text-purple-400">
                      AI
                    </Badge>
                  )}
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6 hover:bg-red-500/20 hover:text-red-400"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDeleteFile(file._id);
                    }}
                  >
                    <Trash2 className="w-3 h-3" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="p-3 border-t border-[#1F1F1F] bg-[#070707]">
        <p className="text-[10px] text-zinc-600 text-center">
          Files stored in Convex
        </p>
      </div>
    </div>
  );
}
