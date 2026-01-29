import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

// Create a file record (for text content)
export const createTextFile = mutation({
  args: {
    projectId: v.id("projects"),
    userId: v.string(),
    name: v.string(),
    path: v.string(),
    type: v.string(),
    content: v.string(),
    isGenerated: v.boolean(),
  },
  handler: async (ctx, args) => {
    const size = new TextEncoder().encode(args.content).length;
    
    return await ctx.db.insert("files", {
      projectId: args.projectId,
      userId: args.userId,
      name: args.name,
      path: args.path,
      type: args.type,
      content: args.content,
      mimeType: getMimeType(args.name),
      size,
      version: 1,
      isGenerated: args.isGenerated,
      createdAt: Date.now(),
      updatedAt: Date.now(),
    });
  },
});

// Create a file record (for binary/storage)
export const createStorageFile = mutation({
  args: {
    projectId: v.id("projects"),
    userId: v.string(),
    name: v.string(),
    path: v.string(),
    type: v.string(),
    storageId: v.id("_storage"),
    size: v.number(),
    isGenerated: v.boolean(),
  },
  handler: async (ctx, args) => {
    return await ctx.db.insert("files", {
      projectId: args.projectId,
      userId: args.userId,
      name: args.name,
      path: args.path,
      type: args.type,
      storageId: args.storageId,
      mimeType: getMimeType(args.name),
      size: args.size,
      version: 1,
      isGenerated: args.isGenerated,
      createdAt: Date.now(),
      updatedAt: Date.now(),
    });
  },
});

// Get files for a project
export const getProjectFiles = query({
  args: { projectId: v.id("projects") },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("files")
      .withIndex("by_project", (q) => q.eq("projectId", args.projectId))
      .collect();
  },
});

// Get a file by ID
export const getFile = query({
  args: { fileId: v.id("files") },
  handler: async (ctx, args) => {
    return await ctx.db.get(args.fileId);
  },
});

// Update file content
export const updateFileContent = mutation({
  args: {
    fileId: v.id("files"),
    content: v.string(),
  },
  handler: async (ctx, args) => {
    const file = await ctx.db.get(args.fileId);
    if (!file) throw new Error("File not found");

    const size = new TextEncoder().encode(args.content).length;
    
    await ctx.db.patch(args.fileId, {
      content: args.content,
      size,
      version: file.version + 1,
      updatedAt: Date.now(),
    });
  },
});

// Delete file
export const deleteFile = mutation({
  args: { fileId: v.id("files") },
  handler: async (ctx, args) => {
    await ctx.db.delete(args.fileId);
  },
});

// Generate upload URL for binary files
export const generateUploadUrl = mutation(async (ctx) => {
  return await ctx.storage.generateUploadUrl();
});

// Helper function to get MIME type from filename
function getMimeType(filename: string): string {
  const ext = filename.split(".").pop()?.toLowerCase();
  const mimeTypes: Record<string, string> = {
    py: "text/x-python",
    js: "text/javascript",
    ts: "text/typescript",
    tsx: "text/typescript",
    jsx: "text/javascript",
    json: "application/json",
    html: "text/html",
    css: "text/css",
    md: "text/markdown",
    txt: "text/plain",
    yaml: "text/yaml",
    yml: "text/yaml",
  };
  return mimeTypes[ext || ""] || "application/octet-stream";
}
