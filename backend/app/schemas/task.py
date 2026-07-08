from pydantic import BaseModel


class TaskResponse(BaseModel):
    id: int
    description: str
    context: str | None = None
    assignee: str | None = None
    deadline: str | None = None
    done: bool
    planfix_task_id: int | None = None
    planfix_sent_at: str | None = None

    model_config = {"from_attributes": True}


class TaskUpdateRequest(BaseModel):
    description: str | None = None
    context: str | None = None
    assignee: str | None = None
    deadline: str | None = None
    done: bool | None = None


class PlanFixSendRequest(BaseModel):
    """Запрос на отправку выбранных задач в PlanFix."""
    task_ids: list[int]
    project_id: int | None = None
    assignee_ids: dict[str, str] | None = None  # "task_id" -> "user:N"
    creator_id: str | None = None                # "user:N"
    deadline: str | None = None                  # "YYYY-MM-DD"


class PlanFixSendResult(BaseModel):
    task_id: int
    planfix_task_id: int | None = None
    success: bool
    error: str | None = None


class PlanFixUserItem(BaseModel):
    id: str     # "user:1", "user:2" etc.
    name: str


class PlanFixProjectItem(BaseModel):
    id: int
    name: str


class PlanFixAssigneeItem(BaseModel):
    id: str
    name: str


class PlanFixAssignerItem(BaseModel):
    id: str
    name: str


class PlanFixTaskItem(BaseModel):
    """Задача PlanFix для диаграммы Ганта."""
    id: int
    name: str
    description: str
    start_date: str | None = None
    end_date: str | None = None
    status_name: str
    status_color: str
    is_active: bool
    assignees: list[PlanFixAssigneeItem]
    assigner: PlanFixAssignerItem | None = None
    project_id: int | None = None
    project_name: str | None = None
