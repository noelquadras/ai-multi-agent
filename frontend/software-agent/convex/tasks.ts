import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

// Create a new task
export const createTask = mutation({
  args: {
    projectId: v.id("projects"),
    userId: v.string(),
    taskId: v.string(),
    prompt: v.string(),
    modelUsed: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    return await ctx.db.insert("tasks", {
      projectId: args.projectId,
      userId: args.userId,
      taskId: args.taskId,
      prompt: args.prompt,
      status: "pending",
      progress: 0,
      modelUsed: args.modelUsed || "ollama",
      startedAt: Date.now(),
    });
  },
});

// Get tasks for a project
export const getProjectTasks = query({
  args: { projectId: v.id("projects") },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("tasks")
      .withIndex("by_project", (q) => q.eq("projectId", args.projectId))
      .order("desc")
      .collect();
  },
});

// Get task by external ID
export const getTaskByExternalId = query({
  args: { taskId: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("tasks")
      .withIndex("by_task_id", (q) => q.eq("taskId", args.taskId))
      .first();
  },
});

// Update task status
export const updateTaskStatus = mutation({
  args: {
    taskId: v.string(),
    status: v.string(),
    currentAgent: v.optional(v.string()),
    progress: v.optional(v.number()),
  },
  handler: async (ctx, args) => {
    const task = await ctx.db
      .query("tasks")
      .withIndex("by_task_id", (q) => q.eq("taskId", args.taskId))
      .first();

    if (!task) throw new Error("Task not found");

    const updates: Record<string, unknown> = { status: args.status };
    if (args.currentAgent !== undefined) updates.currentAgent = args.currentAgent;
    if (args.progress !== undefined) updates.progress = args.progress;
    if (args.status === "completed" || args.status === "failed") {
      updates.completedAt = Date.now();
    }

    await ctx.db.patch(task._id, updates);
  },
});

// Save checkpoint (for pause/resume)
export const saveCheckpoint = mutation({
  args: {
    taskId: v.string(),
    checkpointId: v.string(),
    checkpointState: v.any(),
    currentAgent: v.string(),
    progress: v.number(),
  },
  handler: async (ctx, args) => {
    const task = await ctx.db
      .query("tasks")
      .withIndex("by_task_id", (q) => q.eq("taskId", args.taskId))
      .first();

    if (!task) throw new Error("Task not found");

    await ctx.db.patch(task._id, {
      status: "paused",
      checkpointId: args.checkpointId,
      checkpointState: args.checkpointState,
      currentAgent: args.currentAgent,
      progress: args.progress,
    });
  },
});

// Get checkpoint for resume
export const getCheckpoint = query({
  args: { taskId: v.string() },
  handler: async (ctx, args) => {
    const task = await ctx.db
      .query("tasks")
      .withIndex("by_task_id", (q) => q.eq("taskId", args.taskId))
      .first();

    if (!task || !task.checkpointState) return null;

    return {
      checkpointId: task.checkpointId,
      checkpointState: task.checkpointState,
      currentAgent: task.currentAgent,
      progress: task.progress,
    };
  },
});

// Update task outputs
export const updateTaskOutputs = mutation({
  args: {
    taskId: v.string(),
    outputs: v.object({
      generatedCode: v.optional(v.string()),
      reviewReport: v.optional(v.string()),
      decision: v.optional(v.string()),
      refinedCode: v.optional(v.string()),
      documentation: v.optional(v.string()),
      testResults: v.optional(v.string()),
    }),
  },
  handler: async (ctx, args) => {
    const task = await ctx.db
      .query("tasks")
      .withIndex("by_task_id", (q) => q.eq("taskId", args.taskId))
      .first();

    if (!task) throw new Error("Task not found");

    const currentOutputs = task.outputs || {};
    await ctx.db.patch(task._id, {
      outputs: { ...currentOutputs, ...args.outputs },
    });
  },
});

// Add error to task
export const addTaskError = mutation({
  args: {
    taskId: v.string(),
    error: v.string(),
  },
  handler: async (ctx, args) => {
    const task = await ctx.db
      .query("tasks")
      .withIndex("by_task_id", (q) => q.eq("taskId", args.taskId))
      .first();

    if (!task) throw new Error("Task not found");

    const errors = task.errors || [];
    await ctx.db.patch(task._id, {
      errors: [...errors, args.error],
    });
  },
});
