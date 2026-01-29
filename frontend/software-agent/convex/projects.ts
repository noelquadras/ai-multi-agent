import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

// Create a new project
export const createProject = mutation({
  args: {
    userId: v.string(),
    name: v.string(),
    description: v.optional(v.string()),
    requirements: v.optional(v.string()),
    language: v.optional(v.string()),
    framework: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    return await ctx.db.insert("projects", {
      userId: args.userId,
      name: args.name,
      description: args.description,
      requirements: args.requirements,
      language: args.language,
      framework: args.framework,
      status: "active",
      createdAt: Date.now(),
      updatedAt: Date.now(),
    });
  },
});

// Get all projects for a user
export const getUserProjects = query({
  args: { userId: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("projects")
      .withIndex("by_user", (q) => q.eq("userId", args.userId))
      .order("desc")
      .collect();
  },
});

// Get a single project
export const getProject = query({
  args: { projectId: v.id("projects") },
  handler: async (ctx, args) => {
    return await ctx.db.get(args.projectId);
  },
});

// Update project
export const updateProject = mutation({
  args: {
    projectId: v.id("projects"),
    name: v.optional(v.string()),
    description: v.optional(v.string()),
    requirements: v.optional(v.string()),
    generatedCode: v.optional(v.string()),
    refinedCode: v.optional(v.string()),
    documentation: v.optional(v.string()),
    status: v.optional(v.string()),
    language: v.optional(v.string()),
    framework: v.optional(v.string()),
    githubUrl: v.optional(v.string()),
    modelConfig: v.optional(v.object({
      codeGenModel: v.string(),
      reviewModel: v.string(),
      refineModel: v.string(),
    })),
  },
  handler: async (ctx, args) => {
    const { projectId, ...updates } = args;
    
    // Filter out undefined values
    const filteredUpdates: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(updates)) {
      if (value !== undefined) {
        filteredUpdates[key] = value;
      }
    }
    
    await ctx.db.patch(projectId, {
      ...filteredUpdates,
      updatedAt: Date.now(),
    });
  },
});

// Delete project
export const deleteProject = mutation({
  args: { projectId: v.id("projects") },
  handler: async (ctx, args) => {
    await ctx.db.delete(args.projectId);
  },
});

// Archive project
export const archiveProject = mutation({
  args: { projectId: v.id("projects") },
  handler: async (ctx, args) => {
    await ctx.db.patch(args.projectId, {
      status: "archived",
      updatedAt: Date.now(),
    });
  },
});
