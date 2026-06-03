"""Scheduler Service — cron-based periodic execution for agents.

Runs as a background task when the FastAPI app starts.
Checks every minute for agents that need to be triggered based on their schedule.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from croniter import croniter
from sqlalchemy.orm import Session

from app.backend.database.connection import SessionLocal
from app.backend.database.agent_models import RegisteredAgent, AgentRun
from app.backend.services.context_router import collect_upstream_context
from app.backend.services.agent_trigger import trigger_agent

logger = logging.getLogger(__name__)


class AgentScheduler:
    """Background scheduler that triggers agents based on their cron schedules."""

    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the scheduler background loop."""
        if self._running:
            logger.warning("Scheduler already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Agent scheduler started")

    async def stop(self):
        """Stop the scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Agent scheduler stopped")

    async def _run_loop(self):
        """Main loop — check every 60 seconds for agents to trigger."""
        while self._running:
            try:
                await self._check_and_trigger()
            except Exception as e:
                logger.error(f"Scheduler error: {e}", exc_info=True)

            # Sleep for 60 seconds
            await asyncio.sleep(60)

    async def _check_and_trigger(self):
        """Check all agents with schedules and trigger those that are due."""
        db = SessionLocal()
        try:
            now = datetime.now(timezone.utc)

            # Get all active agents with schedules
            agents = (
                db.query(RegisteredAgent)
                .filter(
                    RegisteredAgent.is_active == True,
                    RegisteredAgent.schedule.isnot(None),
                )
                .all()
            )

            for agent in agents:
                if self._should_trigger(agent, now):
                    await self._trigger_scheduled(db, agent)

        finally:
            db.close()

    def _should_trigger(self, agent: RegisteredAgent, now: datetime) -> bool:
        """Check if an agent should be triggered based on its schedule."""
        if not agent.schedule:
            return False

        try:
            # Get the last run time (or a default if never run)
            last_run = agent.last_run_at or datetime(2000, 1, 1, tzinfo=timezone.utc)

            # Use croniter to find the next scheduled time after last_run
            cron = croniter(agent.schedule, last_run)
            next_run = cron.get_next(datetime)

            # Trigger if the next run time is in the past
            return next_run <= now

        except (ValueError, KeyError) as e:
            logger.error(f"Invalid cron schedule '{agent.schedule}' for agent {agent.name}: {e}")
            return False

    async def _trigger_scheduled(self, db: Session, agent: RegisteredAgent):
        """Trigger a scheduled agent run."""
        run_id = uuid.uuid4().hex[:16]

        # Create run record
        run = AgentRun(
            agent_id=agent.id,
            agent_name=agent.name,
            run_id=run_id,
            status="pending",
            trigger_type="scheduled",
            started_at=datetime.now(timezone.utc),
        )
        db.add(run)
        db.commit()

        # Collect upstream context
        context = collect_upstream_context(db, agent.id)

        # Trigger the agent
        success = await trigger_agent(agent, run_id, context)

        if success:
            run.status = "running"
            logger.info(f"Scheduled trigger: {agent.name} (run_id={run_id})")
        else:
            run.status = "failed"
            run.error_message = "Failed to reach agent endpoint"
            run.completed_at = datetime.now(timezone.utc)
            logger.error(f"Scheduled trigger failed: {agent.name}")

        db.commit()


# Global scheduler instance
agent_scheduler = AgentScheduler()
