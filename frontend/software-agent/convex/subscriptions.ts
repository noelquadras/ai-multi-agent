import { query } from "./_generated/server";
import { v } from "convex/values";

// Subscribe to task events (real-time updates)
export const subscribeToTaskEvents = query({
  args: { taskId: v.id("tasks") },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("events")
      .withIndex("by_task", (q) => q.eq("taskId", args.taskId))
      .order("asc")
      .collect();
  },
});

// Subscribe to project updates
export const subscribeToProject = query({
  args: { projectId: v.id("projects") },
  handler: async (ctx, args) => {
    return await ctx.db.get(args.projectId);
  },
});

// Subscribe to user's projects
export const subscribeToUserProjects = query({
  args: { userId: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("projects")
      .withIndex("by_user", (q) => q.eq("userId", args.userId))
      .order("desc")
      .collect();
  },
});

// Subscribe to project files
export const subscribeToProjectFiles = query({
  args: { projectId: v.id("projects") },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("files")
      .withIndex("by_project", (q) => q.eq("projectId", args.projectId))
      .collect();
  },
});

// Get running tasks for user
export const getRunningTasks = query({
  args: { userId: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("tasks")
      .withIndex("by_user", (q) => q.eq("userId", args.userId))
      .filter((q) => 
        q.or(
          q.eq(q.field("status"), "pending"),
          q.eq(q.field("status"), "running")
        )
      )
      .collect();
  },
});
