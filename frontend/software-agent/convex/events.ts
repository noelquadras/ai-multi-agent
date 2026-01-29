import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

// Create an event
export const createEvent = mutation({
  args: {
    taskId: v.id("tasks"),
    userId: v.string(),
    type: v.string(),
    agent: v.optional(v.string()),
    message: v.optional(v.string()),
    code: v.optional(v.string()),
    data: v.optional(v.any()),
  },
  handler: async (ctx, args) => {
    return await ctx.db.insert("events", {
      taskId: args.taskId,
      userId: args.userId,
      type: args.type,
      agent: args.agent,
      message: args.message,
      code: args.code,
      data: args.data,
      timestamp: Date.now(),
    });
  },
});

// Get events for a task
export const getTaskEvents = query({
  args: { taskId: v.id("tasks") },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("events")
      .withIndex("by_task", (q) => q.eq("taskId", args.taskId))
      .order("asc")
      .collect();
  },
});

// Get events for a task by external ID
export const getTaskEventsByExternalId = query({
  args: { taskId: v.string() },
  handler: async (ctx, args) => {
    // First find the task
    const task = await ctx.db
      .query("tasks")
      .withIndex("by_task_id", (q) => q.eq("taskId", args.taskId))
      .first();

    if (!task) return [];

    return await ctx.db
      .query("events")
      .withIndex("by_task", (q) => q.eq("taskId", task._id))
      .order("asc")
      .collect();
  },
});

// Get recent events for a user
export const getUserRecentEvents = query({
  args: { 
    userId: v.string(),
    limit: v.optional(v.number()),
  },
  handler: async (ctx, args) => {
    const limit = args.limit || 50;
    return await ctx.db
      .query("events")
      .withIndex("by_user", (q) => q.eq("userId", args.userId))
      .order("desc")
      .take(limit);
  },
});
