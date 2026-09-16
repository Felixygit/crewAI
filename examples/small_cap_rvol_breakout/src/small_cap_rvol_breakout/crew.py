"""Small-cap RVOL opening-range breakout crew."""

from __future__ import annotations

from typing import List

from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, crew, task

from small_cap_rvol_breakout.tools.screener_tools import (
    RvolBreakoutTradePlanTool,
    SmallCapRvolScreenerTool,
)


@CrewBase
class SmallCapRvolBreakout:
    """Crew that screens and plans RVOL OR-high breakouts."""

    agents: List[BaseAgent]
    tasks: List[Task]

    @agent
    def market_screener(self) -> Agent:
        return Agent(
            config=self.agents_config["market_screener"],  # type: ignore[index]
            tools=[SmallCapRvolScreenerTool()],
            verbose=True,
        )

    @agent
    def breakout_strategist(self) -> Agent:
        return Agent(
            config=self.agents_config["breakout_strategist"],  # type: ignore[index]
            tools=[RvolBreakoutTradePlanTool()],
            verbose=True,
        )

    @agent
    def risk_officer(self) -> Agent:
        return Agent(
            config=self.agents_config["risk_officer"],  # type: ignore[index]
            verbose=True,
        )

    @task
    def screen_task(self) -> Task:
        return Task(
            config=self.tasks_config["screen_task"],  # type: ignore[index]
        )

    @task
    def plan_task(self) -> Task:
        return Task(
            config=self.tasks_config["plan_task"],  # type: ignore[index]
        )

    @task
    def risk_review_task(self) -> Task:
        return Task(
            config=self.tasks_config["risk_review_task"],  # type: ignore[index]
        )

    @crew
    def crew(self) -> Crew:
        """Create the sequential screening crew."""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
