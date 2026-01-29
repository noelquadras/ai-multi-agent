import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

// Store a memory
export const storeMemory = mutation({
  args: {
    userId: v.string(),
    projectId: v.optional(v.id("projects")),
    type: v.string(),
    key: v.string(),
    value: v.any(),
    importance: v.optional(v.number()),
  },
  handler: async (ctx, args) => {
    // Check if memory with same key exists
    const existing = await ctx.db
      .query("memory")
      .withIndex("by_user", (q) => q.eq("userId", args.userId))
      .filter((q) => q.eq(q.field("key"), args.key))
      .first();

    if (existing) {
      // Update existing memory
      await ctx.db.patch(existing._id, {
        value: args.value,
        importance: args.importance || existing.importance,
        usageCount: existing.usageCount + 1,
        lastUsedAt: Date.now(),
      });
      return existing._id;
    }

    return await ctx.db.insert("memory", {
      userId: args.userId,
      projectId: args.projectId,
      type: args.type,
      key: args.key,
      value: args.value,
      importance: args.importance || 5,
      usageCount: 1,
      createdAt: Date.now(),
      lastUsedAt: Date.now(),
    });
  },
});

// Get memories for a user
export const getUserMemories = query({
  args: { 
    userId: v.string(),
    type: v.optional(v.string()),
    limit: v.optional(v.number()),
  },
  handler: async (ctx, args) => {
    let query = ctx.db
      .query("memory")
      .withIndex("by_user", (q) => q.eq("userId", args.userId));

    if (args.type) {
      query = query.filter((q) => q.eq(q.field("type"), args.type));
    }

    const memories = await query.collect();
    
    // Sort by importance and recency
    memories.sort((a, b) => {
      const importanceDiff = b.importance - a.importance;
      if (importanceDiff !== 0) return importanceDiff;
      return b.lastUsedAt - a.lastUsedAt;
    });

    return args.limit ? memories.slice(0, args.limit) : memories;
  },
});

// Get memories for a project
export const getProjectMemories = query({
  args: { 
    projectId: v.id("projects"),
    type: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    let query = ctx.db
      .query("memory")
      .withIndex("by_project", (q) => q.eq("projectId", args.projectId));

    if (args.type) {
      query = query.filter((q) => q.eq(q.field("type"), args.type));
    }

    return await query.collect();
  },
});

// Update memory usage
export const touchMemory = mutation({
  args: { memoryId: v.id("memory") },
  handler: async (ctx, args) => {
    const memory = await ctx.db.get(args.memoryId);
    if (!memory) return;

    await ctx.db.patch(args.memoryId, {
      usageCount: memory.usageCount + 1,
      lastUsedAt: Date.now(),
    });
  },
});

// Delete memory
export const deleteMemory = mutation({
  args: { memoryId: v.id("memory") },
  handler: async (ctx, args) => {
    await ctx.db.delete(args.memoryId);
  },
});

// Clear old/unused memories
export const clearOldMemories = mutation({
  args: {
    userId: v.string(),
    maxAge: v.number(), // in milliseconds
  },
  handler: async (ctx, args) => {
    const cutoff = Date.now() - args.maxAge;
    const oldMemories = await ctx.db
      .query("memory")
      .withIndex("by_user", (q) => q.eq("userId", args.userId))
      .filter((q) => 
        q.and(
          q.lt(q.field("lastUsedAt"), cutoff),
          q.lt(q.field("importance"), 7)
        )
      )
      .collect();

    for (const memory of oldMemories) {
      await ctx.db.delete(memory._id);
    }

    return oldMemories.length;
  },
});
