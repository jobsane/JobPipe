"""Factory for AuthorAdapter implementations.

Uses importlib for crewai so jobpipe/ never statically imports crewai.
"""
import importlib

from jobpipe.authoring.adapter import AuthorAdapter


def build_author(name: str = "simple", model: str = "gpt-4o-mini") -> AuthorAdapter:
    if name == "simple":
        from jobpipe.authoring.simple_agent_author import SimpleAgentAuthor

        return SimpleAgentAuthor(model=model)
    elif name == "crewai":
        mod = importlib.import_module("jobpipe_crewai.author")
        return mod.CrewAIAuthor(model=model)
    else:
        raise ValueError(f"Unknown author {name!r}. Valid: 'simple', 'crewai'")
