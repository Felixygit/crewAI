"""EMA / VWAP stack educational trade-plan crew."""

from __future__ import annotations

from typing import List

from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, crew, task

from ema_vwap_stack.tools.stack_tools import EmaVwapStackPlanTool, ValidateAndPlanTool


@CrewBase
class EmaVwapStack:
    """Crew that classifies regime, scores confluence, and emits one plan."""

    agents: List[BaseAgent]
    tasks: List[Task]

    @agent
    def regime_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config["regime_analyst"],  # type: ignore[index]
            tools=[EmaVwapStackPlanTool(), ValidateAndPlanTool()],
            verbose=True,
        )

    @agent
    def stack_strategist(self) -> Agent:
        return Agent(
            config=self.agents_config["stack_strategist"],  # type: ignore[index]
            tools=[EmaVwapStackPlanTool()],
            verbose=True,
        )

    @agent
    def risk_scribe(self) -> Agent:
        return Agent(
            config=self.agents_config["risk_scribe"],  # type: ignore[index]
            tools=[EmaVwapStackPlanTool()],
            verbose=True,
        )

    @task
    def regime_task(self) -> Task:
        return Task(
            config=self.tasks_config["regime_task"],  # type: ignore[index]
        )

    @task
    def setup_task(self) -> Task:
        return Task(
            config=self.tasks_config["setup_task"],  # type: ignore[index]
        )

    @task
    def plan_task(self) -> Task:
        return Task(
            config=self.tasks_config["plan_task"],  # type: ignore[index]
        )

    @crew
    def crew(self) -> Crew:
        """Create the sequential stack-planning crew."""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
