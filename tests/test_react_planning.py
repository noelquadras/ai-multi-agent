import unittest


from agents.context import TaskItem
from agents.react_supervisor import PlannerTool, ReactPlan, ensure_plan_object, ensure_task_object


class TestEnsureObjects(unittest.TestCase):
    def test_ensure_task_object_back_compat_task_key(self):
        ti = ensure_task_object({"task": "Do thing", "priority": "high"})
        self.assertEqual(ti.description, "Do thing")
        self.assertEqual(ti.priority, "high")

    def test_ensure_plan_object_from_dict(self):
        plan = ensure_plan_object({"goal": "G", "tasks": [{"description": "A"}]})
        self.assertEqual(plan.goal, "G")
        self.assertEqual(len(plan.tasks), 1)
        self.assertEqual(plan.tasks[0].description, "A")

    def test_ensure_plan_object_from_list(self):
        plan = ensure_plan_object([{"description": "A"}, {"description": "B"}])
        self.assertEqual(plan.goal, "")
        self.assertEqual([t.description for t in plan.tasks], ["A", "B"])


class TestReactPlan(unittest.TestCase):
    def test_get_next_task_respects_dependencies_and_priority(self):
        t1 = TaskItem(description="First", priority="high")
        t2 = TaskItem(description="Blocked", priority="critical", dependencies=[t1.task_id])
        t3 = TaskItem(description="Low", priority="low")
        plan = ReactPlan(goal="X", tasks=[t2, t3, t1])

        # Only t1 and t3 are available; t1 should win due to higher priority.
        next_task = plan.get_next_task()
        self.assertIsNotNone(next_task)
        self.assertEqual(next_task.task_id, t1.task_id)

        plan.complete(t1.task_id)
        next_task = plan.get_next_task()
        self.assertIsNotNone(next_task)
        self.assertEqual(next_task.task_id, t2.task_id)

    def test_is_finished(self):
        t1 = TaskItem(description="A")
        plan = ReactPlan(goal="X", tasks=[t1])
        self.assertFalse(plan.is_finished())
        plan.complete(t1.task_id)
        self.assertTrue(plan.is_finished())


class TestPlannerToolValidation(unittest.TestCase):
    def test_update_requires_new_status(self):
        t1 = TaskItem(description="A")
        plan = ReactPlan(goal="X", tasks=[t1])
        tool = PlannerTool(action="update", task=t1)
        tool._react_plan = plan
        res = tool.validate_action()
        self.assertFalse(res["is_valid"])
        self.assertTrue(any("new_status" in e for e in res["errors"]))

    def test_complete_requires_existing_task_id(self):
        t1 = TaskItem(description="A")
        plan = ReactPlan(goal="X", tasks=[t1])
        missing = TaskItem(description="Missing")
        tool = PlannerTool(action="complete", task=missing)
        tool._react_plan = plan
        res = tool.validate_action()
        self.assertFalse(res["is_valid"])
        self.assertTrue(any("not found" in e for e in res["errors"]))

    def test_append_requires_dependency_present(self):
        t1 = TaskItem(description="A")
        plan = ReactPlan(goal="X", tasks=[t1])
        tool_task = TaskItem(description="B", dependencies=["nope"])
        tool = PlannerTool(action="append", task=tool_task)
        tool._react_plan = plan
        res = tool.validate_action()
        self.assertFalse(res["is_valid"])
        self.assertTrue(any("Dependency task" in e for e in res["errors"]))

    def test_duration_too_long_is_rejected(self):
        plan = ReactPlan(goal="X", tasks=[])
        tool_task = TaskItem(description="Long", estimated_duration=121)
        tool = PlannerTool(action="append", task=tool_task)
        tool._react_plan = plan
        res = tool.validate_action()
        self.assertFalse(res["is_valid"])
        self.assertTrue(any("2 hours" in e for e in res["errors"]))


if __name__ == "__main__":
    unittest.main()
