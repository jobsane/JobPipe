import json

from crewai import Agent, Crew, Process, Task

from jobpipe_crewai.prompts import (
    AUTHOR_SYSTEM,
    AUTHOR_TASK_TEMPLATE,
    CRITIC_SYSTEM,
    CRITIC_TASK_TEMPLATE,
)


def build_authoring_crew(payload: dict, model: str) -> Crew:
    context_str = json.dumps(payload, indent=2)

    author_agent = Agent(
        role="CV and Cover Letter Author",
        goal=(
            "Draft a tailored CV projection and cover letter from candidate evidence. "
            "Only include claims supported by the provided evidence units."
        ),
        backstory=AUTHOR_SYSTEM,
        llm=model,
        verbose=False,
        max_iter=2,
    )

    critic_agent = Agent(
        role="Application Quality Critic",
        goal=(
            "Validate the draft against evidence refs and job claim targets. "
            "Flag unsupported claims, missing evidence, and ATS hygiene issues."
        ),
        backstory=CRITIC_SYSTEM,
        llm=model,
        verbose=False,
        max_iter=2,
    )

    author_task = Task(
        description=AUTHOR_TASK_TEMPLATE.format(context=context_str),
        expected_output=(
            "JSON with: cover_letter_draft (str), tailored_cv_projection (dict), "
            "evidence_refs (list), gap_notes (list)"
        ),
        agent=author_agent,
    )

    critic_task = Task(
        description=CRITIC_TASK_TEMPLATE.format(context=context_str),
        expected_output="JSON with: passed (bool), issues (list), suggestions (list)",
        agent=critic_agent,
        context=[author_task],
    )

    return Crew(
        agents=[author_agent, critic_agent],
        tasks=[author_task, critic_task],
        process=Process.sequential,
        verbose=False,
    )
